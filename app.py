from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import json
import zipfile
import shutil
import glob
import re
import textstat
import nltk
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'store'
app.config['UNPACKED_FOLDER'] = 'unpacked'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max file size
ALLOWED_EXTENSIONS = {'mcworld', 'mctemplate'}

# Create directories if they don't exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['UNPACKED_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Create metadata files if they don't exist
METADATA_FILE = os.path.join(app.config['UPLOAD_FOLDER'], 'metadata.json')
UNPACKED_METADATA_FILE = os.path.join(app.config['UNPACKED_FOLDER'], 'metadata.json')

for metadata_file in [METADATA_FILE, UNPACKED_METADATA_FILE]:
    if not os.path.exists(metadata_file):
        with open(metadata_file, 'w') as f:
            json.dump([], f)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Simple user class for demonstration
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# Demo users (in production, use a proper database)
users = {
    'admin': User('1', 'admin', generate_password_hash('password123')),
    'user': User('2', 'user', generate_password_hash('user123'))
}

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_size_mb(filepath):
    """Get file size in MB"""
    size_bytes = os.path.getsize(filepath)
    return round(size_bytes / (1024 * 1024), 2)

def get_folder_size_mb(folder_path):
    """Get folder size in MB"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return round(total_size / (1024 * 1024), 2)

def load_metadata():
    """Load metadata from JSON file"""
    try:
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def load_unpacked_metadata():
    """Load unpacked metadata from JSON file"""
    try:
        with open(UNPACKED_METADATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_metadata(metadata):
    """Save metadata to JSON file"""
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

def save_unpacked_metadata(metadata):
    """Save unpacked metadata to JSON file"""
    with open(UNPACKED_METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

def migrate_existing_metadata():
    """Add missing fields to existing metadata for backward compatibility"""
    metadata = load_metadata()
    updated = False
    
    for world in metadata:
        if 'unpacked' not in world:
            world['unpacked'] = False
            updated = True
    
    if updated:
        save_metadata(metadata)

# Run migration on startup
migrate_existing_metadata()

def add_file_metadata(filename, original_filename, username):
    """Add file metadata to the store"""
    metadata = load_metadata()
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    file_info = {
        'id': len(metadata) + 1,
        'filename': filename,
        'original_filename': original_filename,
        'uploaded_by': username,
        'upload_date': datetime.now().isoformat(),
        'file_size_mb': get_file_size_mb(file_path),
        'file_type': filename.rsplit('.', 1)[1].lower(),
        'unpacked': False
    }
    
    metadata.append(file_info)
    save_metadata(metadata)
    return file_info

def verify_unpacked_status():
    """Verify and clean up inconsistent unpacked statuses"""
    metadata = load_metadata()
    unpacked_metadata = load_unpacked_metadata()
    needs_update = False
    
    # Create a set of world IDs that actually have unpacked versions
    actually_unpacked = set()
    for unpacked_world in unpacked_metadata:
        original_world_id = unpacked_world.get('original_world_id')
        if original_world_id:
            # Check if the unpacked folder actually exists
            unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_world['folder_name'])
            if os.path.exists(unpacked_path):
                actually_unpacked.add(original_world_id)
    
    # Only clean up worlds that are marked as unpacked but don't actually have unpacked versions
    # Don't try to mark worlds as unpacked if they're not already marked that way
    for world in metadata:
        if world.get('unpacked', False) and world['id'] not in actually_unpacked:
            # World is marked as unpacked but doesn't actually have an unpacked version
            world['unpacked'] = False
            needs_update = True
    
    if needs_update:
        save_metadata(metadata)
    
    return needs_update

def clean_unpacked_metadata():
    """Clean up orphaned unpacked metadata entries"""
    metadata = load_metadata()
    unpacked_metadata = load_unpacked_metadata()
    valid_world_ids = {world['id'] for world in metadata}
    
    # Filter out unpacked entries that don't correspond to existing worlds
    # or whose folders don't exist
    cleaned_unpacked = []
    needs_update = False
    
    for unpacked_world in unpacked_metadata:
        original_world_id = unpacked_world.get('original_world_id')
        folder_name = unpacked_world.get('folder_name')
        
        # Check if the original world still exists
        if original_world_id not in valid_world_ids:
            needs_update = True
            continue
            
        # Check if the unpacked folder still exists
        if folder_name:
            unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], folder_name)
            if not os.path.exists(unpacked_path):
                needs_update = True
                continue
        
        # This unpacked entry is valid
        cleaned_unpacked.append(unpacked_world)
    
    if needs_update:
        save_unpacked_metadata(cleaned_unpacked)
    
    return needs_update

def unpack_world(world_id, username):
    """Unpack a world file and add to unpacked metadata"""
    metadata = load_metadata()
    world = None
    
    # Find the world by ID
    for item in metadata:
        if item['id'] == world_id:
            world = item
            break
    
    if not world:
        return False, "World not found"
    
    # Handle backward compatibility - add 'unpacked' field if it doesn't exist
    if 'unpacked' not in world:
        world['unpacked'] = False

    # Check if world is marked as unpacked
    if world['unpacked']:
        # Verify that the unpacked world actually exists
        unpacked_metadata = load_unpacked_metadata()
        unpacked_exists = False
        
        for unpacked_world in unpacked_metadata:
            if unpacked_world.get('original_world_id') == world_id:
                # Check if the unpacked folder actually exists
                unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_world['folder_name'])
                if os.path.exists(unpacked_path):
                    unpacked_exists = True
                    break
        
        if unpacked_exists:
            return False, "World is already unpacked"
        else:
            # Reset the unpacked status since the unpacked version doesn't actually exist
            world['unpacked'] = False
            save_metadata(metadata)    # Create unique folder name for unpacked world
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder_name = f"{timestamp}_{world['original_filename'].rsplit('.', 1)[0]}"
    unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], folder_name)
    
    try:
        # Extract the zip file
        world_file_path = os.path.join(app.config['UPLOAD_FOLDER'], world['filename'])
        
        with zipfile.ZipFile(world_file_path, 'r') as zip_ref:
            zip_ref.extractall(unpacked_path)
        
        # Calculate folder size
        folder_size_mb = get_folder_size_mb(unpacked_path)
        
        # Add to unpacked metadata
        unpacked_metadata = load_unpacked_metadata()
        unpacked_info = {
            'id': len(unpacked_metadata) + 1,
            'original_world_id': world_id,
            'folder_name': folder_name,
            'original_filename': world['original_filename'],
            'unpacked_by': username,
            'unpacked_date': datetime.now().isoformat(),
            'folder_size_mb': folder_size_mb,
            'file_type': world['file_type']
        }
        
        unpacked_metadata.append(unpacked_info)
        save_unpacked_metadata(unpacked_metadata)
        
        # Mark the original world as unpacked
        world['unpacked'] = True
        world['unpacked_folder'] = folder_name
        save_metadata(metadata)
        
        return True, f"Successfully unpacked \"{world['original_filename']}\""
        
    except zipfile.BadZipFile:
        return False, "Invalid or corrupted world file"
    except Exception as e:
        # Clean up if something went wrong
        if os.path.exists(unpacked_path):
            shutil.rmtree(unpacked_path)
        return False, f"Error unpacking world: {str(e)}"

def repack_world(unpacked_id, username):
    """Repack an unpacked world back into a .mcworld/.mctemplate file with version numbering"""
    try:
        # Get the unpacked world information
        unpacked_world = get_unpacked_world_by_id(unpacked_id)
        if not unpacked_world:
            return False, "Unpacked world not found"
        
        # Path to the unpacked folder
        unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_world['folder_name'])
        if not os.path.exists(unpacked_path):
            return False, "Unpacked world folder not found"
        
        # Generate new filename with version number
        original_name = unpacked_world['original_filename']
        base_name, ext = os.path.splitext(original_name)
        
        # Find next version number by checking existing files
        existing_metadata = load_metadata()
        version = 1
        while True:
            versioned_name = f"{base_name}_v{version}{ext}"
            if not any(world['original_filename'] == versioned_name for world in existing_metadata):
                break
            version += 1
        
        # Create the new repacked file path
        repacked_filename = versioned_name
        repacked_path = os.path.join(app.config['UPLOAD_FOLDER'], repacked_filename)
        
        # Create ZIP file from unpacked folder
        with zipfile.ZipFile(repacked_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(unpacked_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate relative path from unpacked folder
                    relative_path = os.path.relpath(file_path, unpacked_path)
                    zipf.write(file_path, relative_path)
        
        # Get file size
        file_size_mb = get_file_size_mb(repacked_path)
        
        # Add to metadata
        metadata = load_metadata()
        world_info = {
            'id': len(metadata) + 1,
            'original_filename': repacked_filename,
            'filename': repacked_filename,
            'uploaded_by': username,
            'upload_date': datetime.now().isoformat(),
            'file_size_mb': file_size_mb,
            'file_type': unpacked_world['file_type'],
            'unpacked': False,
            'repacked_from': unpacked_world['id'],  # Track that this was repacked
            'repacked_date': datetime.now().isoformat()
        }
        
        metadata.append(world_info)
        save_metadata(metadata)
        
        return True, f"Successfully repacked as \"{repacked_filename}\""
        
    except Exception as e:
        # Clean up if something went wrong
        if 'repacked_path' in locals() and os.path.exists(repacked_path):
            os.remove(repacked_path)
        return False, f"Error repacking world: {str(e)}"

def find_language_files(unpacked_folder_name):
    """Find all .lang files in an unpacked world folder"""
    unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_folder_name)
    
    if not os.path.exists(unpacked_path):
        return []
    
    lang_files = []
    
    # Search for .lang files recursively
    for root, dirs, files in os.walk(unpacked_path):
        for file in files:
            if file.lower().endswith('.lang'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, unpacked_path)
                file_size = os.path.getsize(file_path)
                
                lang_files.append({
                    'name': file,
                    'relative_path': relative_path,
                    'full_path': file_path,
                    'size_bytes': file_size,
                    'size_kb': round(file_size / 1024, 2)
                })
    
    # Sort by file size (largest first)
    lang_files.sort(key=lambda x: x['size_bytes'], reverse=True)
    
    return lang_files

def get_unpacked_world_by_id(unpacked_id):
    """Get unpacked world metadata by ID"""
    unpacked_metadata = load_unpacked_metadata()
    for world in unpacked_metadata:
        if world['id'] == unpacked_id:
            return world
    return None

def extract_text_from_lang_file(file_path):
    """Extract readable text from a .lang file, excluding keys and special characters"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            return ""
        
        # Parse .lang file format (key=value pairs)
        text_values = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                # Get the value part after the = sign
                try:
                    key, value = line.split('=', 1)
                    value = value.strip()
                    
                    # Clean up the value - remove formatting codes and special characters
                    cleaned_value = re.sub(r'§[0-9a-fk-or]', '', value)  # Remove Minecraft color codes
                    cleaned_value = re.sub(r'%[ds%]', '', cleaned_value)  # Remove format placeholders
                    cleaned_value = re.sub(r'\\n', ' ', cleaned_value)    # Replace newlines with spaces
                    cleaned_value = re.sub(r'[{}[\]]', '', cleaned_value) # Remove brackets
                    
                    # Only include values that contain actual text (not just numbers or symbols)
                    if len(cleaned_value.strip()) > 2 and re.search(r'[a-zA-Z]', cleaned_value):
                        text_values.append(cleaned_value.strip())
                except ValueError:
                    # Skip malformed lines
                    continue
        
        return ' '.join(text_values)
    
    except UnicodeDecodeError:
        # Try with different encoding
        try:
            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                content = f.read()
                # Process content same as above...
                text_values = []
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        try:
                            key, value = line.split('=', 1)
                            value = value.strip()
                            cleaned_value = re.sub(r'§[0-9a-fk-or]', '', value)
                            cleaned_value = re.sub(r'%[ds%]', '', cleaned_value)
                            cleaned_value = re.sub(r'\\n', ' ', cleaned_value)
                            cleaned_value = re.sub(r'[{}[\]]', '', cleaned_value)
                            if len(cleaned_value.strip()) > 2 and re.search(r'[a-zA-Z]', cleaned_value):
                                text_values.append(cleaned_value.strip())
                        except ValueError:
                            continue
                return ' '.join(text_values)
        except:
            return ""
    except Exception as e:
        return ""

def analyze_language_complexity(text):
    """Analyze text for various language complexity metrics"""
    if not text or len(text.strip()) < 10:
        return None
    
    try:
        analysis = {
            # Basic statistics
            'word_count': len(text.split()),
            'char_count': len(text),
            'sentence_count': textstat.sentence_count(text),
            'paragraph_count': len([p for p in text.split('\n\n') if p.strip()]),
            
            # Readability scores
            'flesch_reading_ease': round(textstat.flesch_reading_ease(text), 2),
            'flesch_kincaid_grade': round(textstat.flesch_kincaid_grade(text), 2),
            'gunning_fog': round(textstat.gunning_fog(text), 2),
            'smog_index': round(textstat.smog_index(text), 2),
            'automated_readability_index': round(textstat.automated_readability_index(text), 2),
            'coleman_liau_index': round(textstat.coleman_liau_index(text), 2),
            'linsear_write_formula': round(textstat.linsear_write_formula(text), 2),
            'dale_chall_readability_score': round(textstat.dale_chall_readability_score(text), 2),
            
            # Text characteristics
            'avg_sentence_length': round(textstat.avg_sentence_length(text), 2),
            'avg_syllables_per_word': round(textstat.avg_syllables_per_word(text), 2),
            'difficult_words': textstat.difficult_words(text),
            'syllable_count': textstat.syllable_count(text),
            
            # Reading time estimate (words per minute)
            'reading_time_minutes': round(len(text.split()) / 200, 1),  # Average 200 WPM
        }
        
        # Determine reading level and precise target age
        grade_level = analysis['flesch_kincaid_grade']
        
        # Calculate precise target age (grade + 5 years, with minimum of 6 and reasonable caps)
        if grade_level <= 1:
            precise_age = 6
        elif grade_level <= 12:
            precise_age = int(round(grade_level + 5))
        elif grade_level <= 16:
            precise_age = 18
        else:
            precise_age = 22
        
        # Set reading level categories
        if grade_level <= 6:
            analysis['reading_level'] = "Elementary (Grades 1-6)"
        elif grade_level <= 8:
            analysis['reading_level'] = "Middle School (Grades 6-8)"
        elif grade_level <= 12:
            analysis['reading_level'] = "High School (Grades 9-12)"
        elif grade_level <= 16:
            analysis['reading_level'] = "College Level"
        else:
            analysis['reading_level'] = "Graduate Level"
        
        # Set precise target age
        analysis['target_age'] = f"{precise_age} years"
        
        # Interpret Flesch Reading Ease
        ease_score = analysis['flesch_reading_ease']
        if ease_score >= 90:
            analysis['ease_interpretation'] = "Very Easy (5th grade)"
        elif ease_score >= 80:
            analysis['ease_interpretation'] = "Easy (6th grade)"
        elif ease_score >= 70:
            analysis['ease_interpretation'] = "Fairly Easy (7th grade)"
        elif ease_score >= 60:
            analysis['ease_interpretation'] = "Standard (8th-9th grade)"
        elif ease_score >= 50:
            analysis['ease_interpretation'] = "Fairly Difficult (10th-12th grade)"
        elif ease_score >= 30:
            analysis['ease_interpretation'] = "Difficult (College level)"
        else:
            analysis['ease_interpretation'] = "Very Difficult (Graduate level)"
        
        return analysis
        
    except Exception as e:
        return None

def perform_language_analysis(unpacked_folder_name):
    """Find the largest .lang file and perform comprehensive language analysis"""
    try:
        # Find all language files
        lang_files = find_language_files(unpacked_folder_name)
        
        if not lang_files:
            return None, "No language files (.lang) were found in this unpacked world. Language analysis requires at least one .lang file to be present."
        
        # Get the largest file
        largest_file = max(lang_files, key=lambda x: x['size_bytes'])
        
        # Check if the largest file is too small
        if largest_file['size_bytes'] < 100:  # Less than 100 bytes
            return None, f"The largest language file '{largest_file['name']}' is too small ({largest_file['size_kb']} KB) to provide meaningful analysis. Language analysis requires files with substantial text content."
        
        # Extract and analyze text
        text = extract_text_from_lang_file(largest_file['full_path'])
        
        if not text:
            return None, f"Could not extract readable text from '{largest_file['name']}'. The file may be corrupted, empty, or contain only formatting codes without actual text content."
        
        if len(text.strip()) < 50:
            return None, f"Insufficient text content found in '{largest_file['name']}' (only {len(text.strip())} characters of readable text). Language analysis requires at least 50 characters of meaningful text content."
        
        if len(text.split()) < 10:
            return None, f"Insufficient word content found in '{largest_file['name']}' (only {len(text.split())} words). Language analysis requires at least 10 words for reliable metrics."
        
        analysis = analyze_language_complexity(text)
        
        if not analysis:
            return None, f"Unable to analyze text complexity from '{largest_file['name']}'. The text content may not be suitable for readability analysis."
        
        # Add file information to analysis
        analysis['analyzed_file'] = {
            'name': largest_file['name'],
            'path': largest_file['relative_path'],
            'size_kb': largest_file['size_kb'],
            'total_files_found': len(lang_files),
            'extracted_text_words': len(text.split()),
            'extracted_text_chars': len(text)
        }
        
        # Add sample text (first 500 characters)
        analysis['sample_text'] = text[:500] + "..." if len(text) > 500 else text
        analysis['full_text_length'] = len(text)
        
        return analysis, None
        
    except FileNotFoundError:
        return None, "The unpacked world folder could not be found. Please ensure the world has been properly unpacked."
    except PermissionError:
        return None, "Permission denied when accessing language files. Please check file permissions."
    except Exception as e:
        return None, f"Error during analysis: {str(e)}"

@login_manager.user_loader
def load_user(user_id):
    for user in users.values():
        if user.id == user_id:
            return user
    return None

@app.route('/')
def index():
    """Home page - redirects to login if not authenticated, otherwise shows main page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = users.get(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout and redirect to login page"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page for Minecraft Education content management"""
    # Clean up orphaned unpacked metadata and verify unpacked statuses
    clean_unpacked_metadata()
    verify_unpacked_status()
    
    worlds = load_metadata()
    unpacked_worlds = load_unpacked_metadata()
    
    # Sort by upload date (newest first)
    worlds.sort(key=lambda x: x['upload_date'], reverse=True)
    unpacked_worlds.sort(key=lambda x: x['unpacked_date'], reverse=True)
    
    return render_template('dashboard.html', user=current_user, worlds=worlds, unpacked_worlds=unpacked_worlds)

@app.route('/add_world')
@login_required
def add_world():
    """Page to upload new world files"""
    return render_template('add_world.html', user=current_user)

@app.route('/upload_world', methods=['POST'])
@login_required
def upload_world():
    """Handle world file upload"""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('add_world'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('add_world'))
    
    if file and allowed_file(file.filename):
        original_filename = file.filename
        # Create a unique filename to avoid conflicts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{secure_filename(original_filename)}"
        
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Add metadata
            file_info = add_file_metadata(filename, original_filename, current_user.username)
            
            flash(f'Successfully uploaded "{original_filename}"', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f'Error uploading file: {str(e)}', 'error')
            return redirect(url_for('add_world'))
    else:
        flash('Invalid file type. Please upload .mcworld or .mctemplate files only.', 'error')
        return redirect(url_for('add_world'))

@app.route('/unpack_world/<int:world_id>')
@login_required
def unpack_world_route(world_id):
    """Unpack a world file"""
    success, message = unpack_world(world_id, current_user.username)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/repack_world/<int:unpacked_id>')
@login_required
def repack_world_route(unpacked_id):
    """Repack an unpacked world back into a .mcworld/.mctemplate file"""
    success, message = repack_world(unpacked_id, current_user.username)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/download_world/<int:world_id>')
@login_required
def download_world(world_id):
    """Download a world file"""
    metadata = load_metadata()
    world = None
    
    for w in metadata:
        if w['id'] == world_id:
            world = w
            break
    
    if not world:
        flash('World not found', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], world['filename'])
        
        if not os.path.exists(file_path):
            flash('World file not found on disk', 'error')
            return redirect(url_for('dashboard'))
        
        return send_file(file_path, as_attachment=True, download_name=world['original_filename'])
    
    except Exception as e:
        flash(f'Error downloading world: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete_world/<int:world_id>')
@login_required
def delete_world(world_id):
    """Delete a world file"""
    metadata = load_metadata()
    world = None
    world_index = -1
    
    for i, w in enumerate(metadata):
        if w['id'] == world_id:
            world = w
            world_index = i
            break
    
    if not world:
        flash('World not found', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Delete the actual file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], world['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Remove from metadata
        metadata.pop(world_index)
        save_metadata(metadata)
        
        flash(f'Successfully deleted "{world["original_filename"]}"', 'success')
    
    except Exception as e:
        flash(f'Error deleting world: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/language_tools')
@login_required
def language_tools():
    """Language Tools main page"""
    unpacked_worlds = load_unpacked_metadata()
    unpacked_worlds.sort(key=lambda x: x['unpacked_date'], reverse=True)
    return render_template('language_tools.html', user=current_user, unpacked_worlds=unpacked_worlds)

@app.route('/language_tools/<int:unpacked_id>')
@login_required
def language_tools_world(unpacked_id):
    """Language Tools for a specific unpacked world"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('language_tools'))
    
    return render_template('language_tools_world.html', user=current_user, world=world)

@app.route('/find_language_files/<int:unpacked_id>')
@login_required
def find_language_files_route(unpacked_id):
    """Find and list all language files in an unpacked world"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404
    
    try:
        lang_files = find_language_files(world['folder_name'])
        return jsonify({
            'success': True,
            'world': world,
            'language_files': lang_files,
            'total_files': len(lang_files)
        })
    except Exception as e:
        return jsonify({'error': f'Error finding language files: {str(e)}'}), 500

@app.route('/analyze_language/<int:unpacked_id>')
@login_required
def analyze_language_route(unpacked_id):
    """Perform language analysis on the largest .lang file in an unpacked world"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404
    
    try:
        analysis, error = perform_language_analysis(world['folder_name'])
        
        if error:
            return jsonify({'error': error}), 400
        
        if not analysis:
            return jsonify({'error': 'Analysis failed'}), 500
        
        return jsonify({
            'success': True,
            'world': world,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({'error': f'Error during language analysis: {str(e)}'}), 500

@app.route('/view_language_file/<int:unpacked_id>/<path:file_path>')
@login_required
def view_language_file(unpacked_id, file_path):
    """View the contents of a language file"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('language_tools'))
    
    try:
        full_path = os.path.join(app.config['UNPACKED_FOLDER'], world['folder_name'], file_path)
        
        # Security check - ensure the file is within the unpacked folder
        unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], world['folder_name'])
        if not os.path.commonpath([full_path, unpacked_path]) == unpacked_path:
            flash('Invalid file path', 'error')
            return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))
        
        if not os.path.exists(full_path) or not full_path.lower().endswith('.lang'):
            flash('Language file not found', 'error')
            return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))
        
        # Read file contents
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        file_info = {
            'name': os.path.basename(file_path),
            'path': file_path,
            'size': os.path.getsize(full_path),
            'lines': len(content.split('\n'))
        }
        
        return render_template('view_language_file.html', 
                             user=current_user, 
                             world=world, 
                             file_info=file_info,
                             content=content)
    
    except Exception as e:
        flash(f'Error reading file: {str(e)}', 'error')
        return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))

@app.route('/download_language_file/<int:unpacked_id>/<path:file_path>')
@login_required
def download_language_file(unpacked_id, file_path):
    """Download a language file"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('language_tools'))
    
    try:
        full_path = os.path.join(app.config['UNPACKED_FOLDER'], world['folder_name'], file_path)
        
        # Security check - ensure the file is within the unpacked folder
        unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], world['folder_name'])
        if not os.path.commonpath([full_path, unpacked_path]) == unpacked_path:
            flash('Invalid file path', 'error')
            return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))
        
        if not os.path.exists(full_path) or not full_path.lower().endswith('.lang'):
            flash('Language file not found', 'error')
            return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))
        
        return send_file(full_path, as_attachment=True, download_name=os.path.basename(file_path))
    
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))

def generate_language_analysis_pdf(world_info, analysis_data, user_name):
    """Generate a PDF report for language analysis"""
    buffer = io.BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                          rightMargin=72, leftMargin=72,
                          topMargin=72, bottomMargin=18)
    
    # Get styles
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading1']
    subheading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Create custom styles
    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        textColor=colors.darkblue
    )
    
    metric_style = ParagraphStyle(
        'Metric',
        parent=styles['Normal'],
        fontSize=11,
        leftIndent=20,
        spaceAfter=6
    )
    
    # Story container for content
    story = []
    
    # Title
    story.append(Paragraph("Minecraft Education Language Analysis Report", title_style))
    story.append(Spacer(1, 20))
    
    # Report metadata
    report_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    metadata_data = [
        ['Report Generated:', report_date],
        ['Analyzed by:', user_name],
        ['World Name:', world_info['original_filename']],
        ['World Size:', f"{world_info['folder_size_mb']:.2f} MB"],
        ['Upload Date:', world_info.get('upload_date', 'N/A')],
        ['Unpacked Date:', world_info['unpacked_date']]
    ]
    
    metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
    metadata_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    story.append(metadata_table)
    story.append(Spacer(1, 20))
    
    # Analysis Overview
    story.append(Paragraph("Analysis Overview", heading_style))
    
    file_info = analysis_data.get('analyzed_file', {})
    overview_data = [
        ['Language File Analyzed:', file_info.get('name', 'Unknown')],
        ['File Size:', f"{file_info.get('size_kb', 0):.1f} KB"],
        ['Total Language Files Found:', str(file_info.get('total_files_found', 0))],
        ['Extracted Text Length:', f"{file_info.get('extracted_text_chars', 0):,} characters"],
        ['Word Count:', f"{file_info.get('extracted_text_words', 0):,} words"]
    ]
    
    overview_table = Table(overview_data, colWidths=[2.5*inch, 3.5*inch])
    overview_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    story.append(overview_table)
    story.append(Spacer(1, 20))
    
    # Readability Metrics
    story.append(Paragraph("Readability Analysis", heading_style))
    
    # Basic Metrics
    story.append(Paragraph("Basic Text Metrics", subtitle_style))
    basic_metrics = [
        f"<b>Sentences:</b> {analysis_data.get('sentence_count', 'N/A')}",
        f"<b>Words:</b> {analysis_data.get('word_count', 'N/A')}",
        f"<b>Characters:</b> {analysis_data.get('char_count', 'N/A')}",
        f"<b>Syllables:</b> {analysis_data.get('syllable_count', 'N/A')}",
        f"<b>Average Words per Sentence:</b> {analysis_data.get('avg_sentence_length', 'N/A')}",
        f"<b>Average Syllables per Word:</b> {analysis_data.get('avg_syllables_per_word', 'N/A')}"
    ]
    
    for metric in basic_metrics:
        story.append(Paragraph(metric, metric_style))
    
    story.append(Spacer(1, 12))
    
    # Reading Level Scores
    story.append(Paragraph("Reading Level Scores", subtitle_style))
    reading_scores = [
        f"<b>Flesch Reading Ease:</b> {analysis_data.get('flesch_reading_ease', 'N/A')} ({analysis_data.get('flesch_reading_ease_desc', 'N/A')})",
        f"<b>Flesch-Kincaid Grade Level:</b> {analysis_data.get('flesch_kincaid_grade', 'N/A')}",
        f"<b>Gunning Fog Index:</b> {analysis_data.get('gunning_fog', 'N/A')}",
        f"<b>SMOG Index:</b> {analysis_data.get('smog_index', 'N/A')}",
        f"<b>Coleman-Liau Index:</b> {analysis_data.get('coleman_liau_index', 'N/A')}",
        f"<b>Automated Readability Index:</b> {analysis_data.get('automated_readability_index', 'N/A')}"
    ]
    
    for score in reading_scores:
        story.append(Paragraph(score, metric_style))
    
    story.append(Spacer(1, 12))
    
    # Educational Recommendations
    story.append(Paragraph("Educational Recommendations", subtitle_style))
    recommendations = analysis_data.get('educational_recommendations', [])
    if recommendations:
        for rec in recommendations:
            story.append(Paragraph(f"• {rec}", metric_style))
    else:
        story.append(Paragraph("No specific recommendations available.", metric_style))
    
    story.append(Spacer(1, 20))
    
    # Sample Text
    story.append(Paragraph("Sample Text", heading_style))
    sample_text = analysis_data.get('sample_text', 'No sample text available')
    story.append(Paragraph(f"<i>{sample_text}</i>", normal_style))
    
    # Build PDF
    doc.build(story)
    
    # Get the value of the BytesIO buffer and return it
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

@app.route('/download_analysis_pdf/<int:unpacked_id>')
@login_required
def download_analysis_pdf(unpacked_id):
    """Generate and download PDF report for language analysis"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('language_tools'))
    
    try:
        # Perform language analysis
        analysis, error = perform_language_analysis(world['folder_name'])
        
        if error:
            flash(f'Cannot generate PDF report: {error}', 'error')
            return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))
        
        # Generate PDF
        pdf_data = generate_language_analysis_pdf(world, analysis, current_user.username)
        
        # Create filename
        safe_filename = secure_filename(world['original_filename'])
        filename = f"language_analysis_{safe_filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Return PDF as download
        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error generating PDF report: {str(e)}', 'error')
        return redirect(url_for('language_tools_world', unpacked_id=unpacked_id))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)