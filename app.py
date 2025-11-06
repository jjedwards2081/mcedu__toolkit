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
from spellchecker import SpellChecker
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import io
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'store'
app.config['UNPACKED_FOLDER'] = 'unpacked'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max file size

# Azure OpenAI Configuration - loaded from environment variables
AZURE_OPENAI_API_KEY = os.getenv('AZURE_OPENAI_API_KEY')
AZURE_OPENAI_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_API_VERSION = os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-5-chat')

# Initialize Azure OpenAI client with error handling
azure_openai_client = None
AI_FEATURES_AVAILABLE = False
AI_STATUS_MESSAGE = ""

try:
    if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT:
        raise ValueError("Azure OpenAI configuration missing: API key or endpoint not found in environment variables")
    
    azure_openai_client = AzureOpenAI(
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY
    )
    AI_FEATURES_AVAILABLE = True
    AI_STATUS_MESSAGE = "AI-powered educational resource generation is active"
    print("Azure OpenAI client initialized successfully")
except Exception as e:
    AI_FEATURES_AVAILABLE = False
    AI_STATUS_MESSAGE = f"AI features unavailable: {str(e)}. These features require Azure OpenAI configuration to function."
    print(f"Warning: Could not initialize Azure OpenAI client: {e}")
    print("Educational resources will use traditional generation methods")

# AI Helper Functions
def call_azure_openai(prompt, max_tokens=2000, temperature=0.7):
    """Call Azure OpenAI with error handling"""
    if azure_openai_client is None:
        print("Azure OpenAI client not available, using fallback method")
        return None
        
    try:
        print(f"Calling Azure OpenAI with prompt length: {len(prompt)} characters")
        response = azure_openai_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a professional educational document generator specializing in Minecraft Education. Create clean, structured educational materials without any conversational elements, greetings, or chat responses. Focus exclusively on producing well-formatted lesson plans, assessments, and educational content. Do not include phrases like 'Here's your lesson plan' or 'I hope this helps'. Start directly with the educational content using proper markdown formatting with headers, lists, and structured sections. Always refer to the platform as 'Minecraft Education' not 'Minecraft Education Edition'."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=1.0
        )
        print(f"Azure OpenAI response received successfully, length: {len(response.choices[0].message.content)} characters")
        return response.choices[0].message.content
    except Exception as e:
        print(f"Azure OpenAI Error: {str(e)}")
        print(f"Error details: {type(e).__name__}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return None

def extract_educational_context(world_data):
    """Extract comprehensive educational context from world data for AI prompts"""
    # Extract core content from language files
    educational_content = world_data.get('educational_content', '')
    primary_file = world_data.get('primary_language_file', 'Educational World')
    
    # Extract NPC dialogue and educational text from the content
    npc_content = extract_npc_content(educational_content)
    learning_content = extract_learning_content(educational_content)
    
    context = {
        'themes': world_data.get('themes', []),
        'learning_objectives': world_data.get('learning_objectives', []),
        'key_concepts': world_data.get('key_concepts', []),
        'educational_content': educational_content,
        'npc_dialogue': npc_content,
        'learning_content': learning_content,
        'age_range': world_data.get('world_info', {}).get('estimated_age_range', 'Middle School'),
        'reading_level': world_data.get('world_info', {}).get('reading_level_description', 'Grade 6-8'),
        'complexity_level': world_data.get('world_info', {}).get('complexity_level', 'Intermediate'),
        'world_name': primary_file.replace('.lang', '').replace('_', ' ').title(),
        'world_features': {
            'has_behavior_packs': world_data.get('world_info', {}).get('has_behavior_packs', False),
            'has_resource_packs': world_data.get('world_info', {}).get('has_resource_packs', False),
            'has_structures': world_data.get('world_info', {}).get('has_structures', False)
        }
    }
    return context

def extract_npc_content(educational_text):
    """Extract NPC dialogue and character interactions from educational content"""
    if not educational_text:
        return []
    
    npc_patterns = [
        r'(.*(?:say|tell|ask|explain|teach|guide|help|welcome|greet).*)',
        r'(.*(?:npc|character|guide|teacher|mentor|advisor).*)',
        r'(.*(?:hello|hi|welcome|good|thanks|please|help).*)',
        r'(.*(?:quest|task|mission|challenge|activity|lesson).*)',
        r'(.*(?:learn|discover|explore|find|collect|build|create).*)'
    ]
    
    npc_content = []
    sentences = educational_text.split('.')
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 10 and len(sentence) < 200:
            for pattern in npc_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    npc_content.append(sentence)
                    break
    
    return npc_content[:10]  # Return top 10 NPC-related content pieces

def extract_learning_content(educational_text):
    """Extract specific learning content and instructional text"""
    if not educational_text:
        return []
    
    learning_patterns = [
        r'(.*(?:students?|learn|study|understand|know|remember|identify).*)',
        r'(.*(?:objective|goal|aim|purpose|skill|knowledge).*)',
        r'(.*(?:instruction|direction|step|process|method|way).*)',
        r'(.*(?:example|for instance|such as|including|like).*)',
        r'(.*(?:important|key|main|primary|essential|crucial).*)'
    ]
    
    learning_content = []
    sentences = educational_text.split('.')
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 15 and len(sentence) < 300:
            for pattern in learning_patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    learning_content.append(sentence)
                    break
    
    return learning_content[:15]  # Return top 15 learning-related content pieces

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

# Context processor to make AI status available to all templates
@app.context_processor
def inject_ai_status():
    return {
        'ai_features_available': AI_FEATURES_AVAILABLE,
        'ai_status_message': AI_STATUS_MESSAGE
    }

# Simple user class for demonstration
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        
    def is_admin(self):
        """Check if user is admin"""
        return is_admin(self.username)
    
    def get_full_name(self):
        """Get user's full name"""
        return get_user_full_name(self.username)
    
    def get_first_name(self):
        """Get user's first name"""
        users_data = get_users_data()
        return users_data.get(self.username, {}).get('first_name', '')
    
    def get_email(self):
        """Get user's email"""
        users_data = get_users_data()
        return users_data.get(self.username, {}).get('email', '')

# User storage file
USERS_FILE = 'users.json'

def load_users():
    """Load users from JSON file"""
    try:
        with open(USERS_FILE, 'r') as f:
            users_data = json.load(f)
            users = {}
            for username, user_data in users_data.items():
                users[username] = User(user_data['id'], user_data['username'], user_data['password_hash'])
            return users
    except FileNotFoundError:
        # Create default admin user if file doesn't exist
        default_users = {
            'admin': {
                'id': '1',
                'username': 'admin',
                'password_hash': generate_password_hash('password123', method='pbkdf2:sha256'),
                'first_name': 'System',
                'surname': 'Administrator',
                'email': 'admin@mcedu-toolkit.local',
                'is_admin': True,
                'created_date': datetime.now().isoformat()
            }
        }
        save_users_to_file(default_users)
        users = {}
        for username, user_data in default_users.items():
            users[username] = User(user_data['id'], user_data['username'], user_data['password_hash'])
        return users
    except:
        return {}

def save_users_to_file(users_data):
    """Save users data to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f, indent=2)

def get_users_data():
    """Get raw users data from file"""
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def is_admin(username):
    """Check if user is admin"""
    users_data = get_users_data()
    return users_data.get(username, {}).get('is_admin', False)

def get_user_full_name(username):
    """Get user's full name"""
    users_data = get_users_data()
    user_data = users_data.get(username, {})
    first_name = user_data.get('first_name', '')
    surname = user_data.get('surname', '')
    full_name = f"{first_name} {surname}".strip()
    return full_name if full_name else username

def get_next_user_id():
    """Get next available user ID"""
    users_data = get_users_data()
    if not users_data:
        return '1'
    max_id = max(int(user['id']) for user in users_data.values())
    return str(max_id + 1)

def create_user(username, password, first_name, surname, email, is_admin=False):
    """Create a new user"""
    users_data = get_users_data()
    
    if username in users_data:
        return False, "Username already exists"
    
    # Check if email already exists
    for user_data in users_data.values():
        if user_data.get('email', '').lower() == email.lower():
            return False, "Email address already exists"
    
    user_id = get_next_user_id()
    users_data[username] = {
        'id': user_id,
        'username': username,
        'password_hash': generate_password_hash(password, method='pbkdf2:sha256'),
        'first_name': first_name.strip(),
        'surname': surname.strip(),
        'email': email.lower().strip(),
        'is_admin': is_admin,
        'created_date': datetime.now().isoformat()
    }
    
    save_users_to_file(users_data)
    return True, "User created successfully"

def delete_user_and_data(username):
    """Delete user and all associated data"""
    if username == 'admin':
        return False, "Cannot delete admin user"
    
    users_data = get_users_data()
    if username not in users_data:
        return False, "User not found"
    
    try:
        # Remove user from users data
        del users_data[username]
        save_users_to_file(users_data)
        
        # Clean up user's uploaded worlds
        metadata = load_metadata()
        worlds_to_remove = []
        for i, world in enumerate(metadata):
            if world.get('uploaded_by') == username:
                # Delete the actual file
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], world['filename'])
                if os.path.exists(file_path):
                    os.remove(file_path)
                worlds_to_remove.append(i)
        
        # Remove worlds from metadata (in reverse order to maintain indices)
        for i in reversed(worlds_to_remove):
            metadata.pop(i)
        save_metadata(metadata)
        
        # Clean up user's unpacked worlds
        unpacked_metadata = load_unpacked_metadata()
        unpacked_to_remove = []
        for i, unpacked_world in enumerate(unpacked_metadata):
            if unpacked_world.get('unpacked_by') == username:
                # Delete the unpacked folder
                unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_world['folder_name'])
                if os.path.exists(unpacked_path):
                    shutil.rmtree(unpacked_path)
                unpacked_to_remove.append(i)
        
        # Remove unpacked worlds from metadata (in reverse order to maintain indices)
        for i in reversed(unpacked_to_remove):
            unpacked_metadata.pop(i)
        save_unpacked_metadata(unpacked_metadata)
        
        return True, f"User '{username}' and all associated data deleted successfully"
    
    except Exception as e:
        return False, f"Error deleting user data: {str(e)}"

# Load users on startup
users = load_users()

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

def migrate_existing_users():
    """Add missing fields to existing users for backward compatibility"""
    users_data = get_users_data()
    updated = False
    
    for username, user_data in users_data.items():
        # Add missing fields with default values
        if 'first_name' not in user_data:
            user_data['first_name'] = username.title()  # Use username as default first name
            updated = True
        
        if 'surname' not in user_data:
            user_data['surname'] = 'User'  # Default surname
            updated = True
        
        if 'email' not in user_data:
            user_data['email'] = f"{username}@example.com"  # Default email
            updated = True
    
    if updated:
        save_users_to_file(users_data)

# Run migrations on startup
migrate_existing_metadata()
migrate_existing_users()

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
    """Find all .lang files in an unpacked world folder, prioritizing English language files"""
    unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_folder_name)
    
    if not os.path.exists(unpacked_path):
        return []
    
    def is_english_lang_file(filename):
        """Check if the filename indicates an English language file"""
        filename_lower = filename.lower()
        english_patterns = [
            'en_us.lang',    # US English
            'en_gb.lang',    # British English  
            'en_ca.lang',    # Canadian English
            'en_au.lang',    # Australian English
            'en.lang',       # Generic English
            'english.lang',  # Named English
            'us.lang',       # US variant
        ]
        
        # Check exact matches first
        if filename_lower in english_patterns:
            return True
            
        # Check if filename contains english indicators
        english_indicators = ['en_', 'english', '_us', '_en']
        return any(indicator in filename_lower for indicator in english_indicators)
    
    lang_files = []
    english_files = []
    other_files = []
    
    # Search for .lang files recursively
    for root, dirs, files in os.walk(unpacked_path):
        for file in files:
            if file.lower().endswith('.lang'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, unpacked_path)
                file_size = os.path.getsize(file_path)
                
                file_info = {
                    'name': file,
                    'relative_path': relative_path,
                    'full_path': file_path,
                    'size_bytes': file_size,
                    'size_kb': round(file_size / 1024, 2),
                    'is_english': is_english_lang_file(file),
                    'language_code': extract_language_code(file)
                }
                
                # Separate English files from others
                if file_info['is_english']:
                    english_files.append(file_info)
                else:
                    other_files.append(file_info)
    
    # Sort English files by size (largest first)
    english_files.sort(key=lambda x: x['size_bytes'], reverse=True)
    
    # Sort other files by size (largest first)  
    other_files.sort(key=lambda x: x['size_bytes'], reverse=True)
    
    # Prioritize English files - put them first in the list
    lang_files = english_files + other_files
    
    return lang_files

def extract_language_code(filename):
    """Extract language code from filename for display purposes"""
    filename_lower = filename.lower()
    
    # Common language patterns
    language_codes = {
        'en_us': 'English (US)',
        'en_gb': 'English (UK)', 
        'en_ca': 'English (Canada)',
        'en_au': 'English (Australia)',
        'en': 'English',
        'us': 'English (US)',
        'english': 'English',
        'es_es': 'Spanish (Spain)',
        'es_mx': 'Spanish (Mexico)',
        'fr_fr': 'French (France)',
        'fr_ca': 'French (Canada)',
        'de_de': 'German',
        'it_it': 'Italian',
        'pt_br': 'Portuguese (Brazil)',
        'pt_pt': 'Portuguese (Portugal)',
        'ru_ru': 'Russian',
        'zh_cn': 'Chinese (Simplified)',
        'zh_tw': 'Chinese (Traditional)',
        'ja_jp': 'Japanese',
        'ko_kr': 'Korean'
    }
    
    # Remove .lang extension
    base_name = filename_lower.replace('.lang', '')
    
    # Check for exact matches
    if base_name in language_codes:
        return language_codes[base_name]
    
    # Check for partial matches
    for code, language in language_codes.items():
        if code in base_name:
            return language
    
    # Default for unknown
    return 'Unknown'

def get_unpacked_world_by_id(unpacked_id):
    """Get unpacked world metadata by ID"""
    unpacked_metadata = load_unpacked_metadata()
    for world in unpacked_metadata:
        if world['id'] == unpacked_id:
            return world
    return None

def is_educational_content(key, value):
    """Determine if this key-value pair contains educational content that users see"""
    key_lower = key.lower()
    
    # Include patterns that indicate educational/user-facing content
    educational_patterns = [
        # NPC and character dialog
        r'npc\.|character\.|\.dialog\.|\.dialogue\.',
        # Educational content and instructions
        r'lesson\.|tutorial\.|instruction\.|guide\.|help\.',
        # Story and narrative content
        r'story\.|narrative\.|text\.|message\.|description\.',
        # Signs and books content
        r'sign\.|book\.|page\.|chapter\.',
        # Chat and conversation
        r'chat\.|conversation\.|speak\.|say\.',
        # Educational activities
        r'activity\.|exercise\.|task\.|quest\.|mission\.',
        # Custom content entries (often educational)
        r'custom\.|edu\.|learn\.|teach\.',
        # World-specific content
        r'world\.|level\.|stage\.',
        # Minecraft Education specific patterns
        r'\.name\.',  # Names/titles for educational elements
        r'\.title\.',  # Titles
        r'convo\.',   # Conversations
        r'dialogue\.',  # Dialogue
        # Common educational prefixes in MC:EE
        r'agent\.',   # Agent activities
        r'board\.',   # Chalkboard/whiteboard content
        r'slate\.',   # Slate content
        r'poster\.'   # Poster content
    ]
    
    # Check if key matches educational patterns
    for pattern in educational_patterns:
        if re.search(pattern, key_lower):
            return True
    
    # Additional checks for value content
    if len(value.strip()) < 3:  # Skip very short values
        return False
    
    # Check if value looks like readable text
    value_lower = value.lower()
    
    # Skip technical values
    if any(tech in value_lower for tech in ['minecraft:', 'textures/', 'sounds/', 'models/', 'blockbench', '{', '}', '[', ']']):
        return False
    
    # Skip pure numbers or codes
    if value.strip().replace('.', '').replace(',', '').replace(' ', '').isdigit():
        return False
    
    # Skip single words unless they appear to be educational
    words = value.split()
    if len(words) == 1:
        educational_words = ['lesson', 'tutorial', 'help', 'guide', 'story', 'welcome', 'instruction', 'activity']
        if not any(edu_word in value_lower for edu_word in educational_words):
            return False
    
    # Check for sentence-like structure (contains common words, punctuation, or is longer)
    sentence_indicators = ['.', '!', '?', ',', 'the ', 'a ', 'an ', 'and ', 'or ', 'but ', 'with ', 'to ', 'for ', 'of ', 'in ', 'on ', 'at ']
    has_sentence_structure = any(indicator in value_lower for indicator in sentence_indicators) or len(words) >= 4
    
    return has_sentence_structure

def extract_text_from_lang_file(file_path):
    """Extract educational content from a .lang file, filtering out technical and system content"""
    
    def clean_educational_text(text):
        """Clean text while preserving educational content structure"""
        # Remove Minecraft formatting codes
        text = re.sub(r'§[0-9a-fk-or]', '', text)
        
        # Remove technical placeholders but keep readable ones
        text = re.sub(r'%[0-9]*[ds]', '[value]', text)  # Replace %d, %s with placeholder
        text = re.sub(r'%[a-zA-Z_][a-zA-Z0-9_]*%', '[value]', text)  # Replace %variable%
        
        # Clean up newlines and spacing
        text = re.sub(r'\\n', ' ', text)
        text = re.sub(r'\n+', ' ', text)
        
        # Remove excessive brackets but keep some structure
        text = re.sub(r'\[{2,}', '[', text)
        text = re.sub(r']{2,}', ']', text)
        text = re.sub(r'[{}]', '', text)
        
        # Clean up multiple spaces and punctuation
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s*([.!?])\s*', r'\1 ', text)
        
        # Remove standalone numbers and very short fragments
        words = text.split()
        words = [w for w in words if not (w.isdigit() and len(w) < 3)]
        
        return ' '.join(words).strip()
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            return ""
        
        educational_text = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                try:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Skip empty values
                    if not value:
                        continue
                    
                    # Filter for educational content
                    if is_educational_content(key, value):
                        cleaned_text = clean_educational_text(value)
                        
                        # Final quality check - must have substantial readable content
                        if (len(cleaned_text) > 10 and 
                            re.search(r'[a-zA-Z]', cleaned_text) and
                            len(cleaned_text.split()) >= 3):
                            educational_text.append(cleaned_text)
                
                except ValueError:
                    continue
        
        # Join all educational text
        result = ' '.join(educational_text)
        
        # Final cleanup pass
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result
    
    except UnicodeDecodeError:
        # Try with different encoding
        try:
            with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                content = f.read()
            
            educational_text = []
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    try:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if not value:
                            continue
                        
                        if is_educational_content(key, value):
                            cleaned_text = clean_educational_text(value)
                            
                            if (len(cleaned_text) > 10 and 
                                re.search(r'[a-zA-Z]', cleaned_text) and
                                len(cleaned_text.split()) >= 3):
                                educational_text.append(cleaned_text)
                    
                    except ValueError:
                        continue
            
            result = ' '.join(educational_text)
            return re.sub(r'\s+', ' ', result).strip()
            
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
    """Find English language files and perform comprehensive language analysis"""
    try:
        # Find all language files
        lang_files = find_language_files(unpacked_folder_name)
        
        if not lang_files:
            return None, "No language files (.lang) were found in this unpacked world. Language analysis requires at least one .lang file to be present."
        
        # Separate English files from others
        english_files = [f for f in lang_files if f['is_english']]
        non_english_files = [f for f in lang_files if not f['is_english']]
        
        # Prioritize English files for analysis
        if english_files:
            # Use the largest English file
            largest_file = max(english_files, key=lambda x: x['size_bytes'])
            analysis_note = f"Analyzing English language file: {largest_file['name']} ({largest_file['language_code']})"
        else:
            # Warn if no English files found, but proceed with largest available
            largest_file = max(lang_files, key=lambda x: x['size_bytes'])
            analysis_note = f"⚠️ No English language files found. Analyzing {largest_file['name']} ({largest_file['language_code']}) - results may not be accurate for English readability assessment."
        
        # Check if the largest file is too small
        if largest_file['size_bytes'] < 100:  # Less than 100 bytes
            language_summary = f"Found {len(english_files)} English file(s) and {len(non_english_files)} other language file(s)."
            return None, f"The selected language file '{largest_file['name']}' ({largest_file['language_code']}) is too small ({largest_file['size_kb']} KB) to provide meaningful analysis. {language_summary} Language analysis requires files with substantial text content."
        
        # Get statistics about the raw file content first
        try:
            with open(largest_file['full_path'], 'r', encoding='utf-8', errors='ignore') as f:
                raw_content = f.read()
            
            raw_lines = [line.strip() for line in raw_content.split('\n') 
                        if line.strip() and not line.strip().startswith('#') and '=' in line]
            total_entries = len(raw_lines)
            
        except:
            total_entries = 0
        
        # Extract and analyze educational text
        text = extract_text_from_lang_file(largest_file['full_path'])
        
        if not text:
            return None, f"Could not extract educational content from '{largest_file['name']}'. The file may contain only technical/system content or be corrupted. Found {total_entries} total entries, but none appear to contain user-facing educational content."
        
        if len(text.strip()) < 50:
            return None, f"Insufficient educational content found in '{largest_file['name']}' (only {len(text.strip())} characters of user-facing text). Out of {total_entries} total entries, very few contained educational content suitable for analysis."
        
        if len(text.split()) < 15:  # Increased threshold for educational content
            return None, f"Insufficient educational content found in '{largest_file['name']}' (only {len(text.split())} words of user-facing text). Language analysis requires at least 15 words of educational content for reliable metrics."
        
        analysis = analyze_language_complexity(text)
        
        if not analysis:
            return None, f"Unable to analyze text complexity from the educational content in '{largest_file['name']}'. The filtered text content may not be suitable for readability analysis."
        
        # Calculate filtering statistics
        educational_entries = len([word for word in text.split() if len(word) > 2]) // 8  # Rough estimate
        filtered_percentage = round((educational_entries / max(total_entries, 1)) * 100, 1) if total_entries > 0 else 0
        
        # Add enhanced file information to analysis
        analysis['analyzed_file'] = {
            'name': largest_file['name'],
            'path': largest_file['relative_path'],
            'size_kb': largest_file['size_kb'],
            'language_code': largest_file['language_code'],
            'is_english': largest_file['is_english'],
            'total_files_found': len(lang_files),
            'english_files_found': len(english_files),
            'non_english_files_found': len(non_english_files),
            'total_entries': total_entries,
            'educational_entries_estimated': educational_entries,
            'content_filtered_percentage': filtered_percentage,
            'extracted_text_words': len(text.split()),
            'extracted_text_chars': len(text),
            'analysis_note': analysis_note
        }
        
        # Add filtering explanation
        analysis['filtering_info'] = {
            'description': 'Content filtered to focus on educational text that users actually see',
            'included_types': [
                'NPC dialogue and character interactions',
                'Instructional and tutorial content', 
                'Story and narrative text',
                'Educational activities and lessons',
                'Signs and book content',
                'Custom world-specific educational content'
            ],
            'excluded_types': [
                'Technical system messages',
                'UI elements and menu items',
                'Command and function references',
                'Block, item, and entity identifiers',
                'Server and multiplayer technical content',
                'Achievement and advancement system text',
                'Inventory and game mechanic labels'
            ],
            'quality_note': f'Analysis based on {filtered_percentage}% of file content identified as educational'
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

def perform_spell_check(unpacked_folder_name):
    """Find English language files and perform comprehensive spell checking"""
    try:
        # Find all language files
        lang_files = find_language_files(unpacked_folder_name)
        
        if not lang_files or lang_files is None:
            return None, "No language files (.lang) were found in this unpacked world. Spell checking requires at least one .lang file to be present."
        
        # Ensure lang_files is a list
        if not isinstance(lang_files, list):
            return None, f"Error: Expected list of language files, got {type(lang_files)}. Please try again."
        
        # Separate English files from others
        english_files = [f for f in lang_files if f and f.get('is_english', False)]
        non_english_files = [f for f in lang_files if f and not f.get('is_english', False)]
        
        # Prioritize English files for spell checking
        if english_files:
            # Use the largest English file
            try:
                largest_file = max(english_files, key=lambda x: x.get('size_bytes', 0))
                spell_check_note = f"Spell checking English language file: {largest_file['name']} ({largest_file.get('language_code', 'Unknown')})"
            except (ValueError, TypeError) as e:
                return None, f"Error selecting English language file: {str(e)}. Files found: {len(english_files)}"
        else:
            # Warn if no English files found, but proceed with largest available
            try:
                largest_file = max(lang_files, key=lambda x: x.get('size_bytes', 0))
                spell_check_note = f"⚠️ No English language files found. Spell checking {largest_file['name']} ({largest_file.get('language_code', 'Unknown')}) - results may include non-English words as errors."
            except (ValueError, TypeError) as e:
                return None, f"Error selecting language file: {str(e)}. Files found: {len(lang_files)}"
        
        # Check if the largest file is too small
        if largest_file['size_bytes'] < 100:  # Less than 100 bytes
            language_summary = f"Found {len(english_files)} English file(s) and {len(non_english_files)} other language file(s)."
            return None, f"The selected language file '{largest_file['name']}' ({largest_file['language_code']}) is too small ({largest_file['size_kb']} KB) to provide meaningful spell checking. {language_summary} Spell checking requires files with substantial text content."
        
        # Extract educational text for spell checking
        try:
            text = extract_text_from_lang_file(largest_file['full_path'])
        except Exception as e:
            return None, f"Error extracting text from '{largest_file['name']}': {str(e)}"
        
        if not text or text is None:
            return None, f"Could not extract educational content from '{largest_file['name']}'. The file may contain only technical/system content or be corrupted."
        
        if len(text.strip()) < 50:
            return None, f"Insufficient educational content found in '{largest_file['name']}' (only {len(text.strip())} characters of user-facing text). Spell checking requires at least 50 characters of educational content."
        
        if len(text.split()) < 15:  # Increased threshold for educational content
            return None, f"Insufficient educational content found in '{largest_file['name']}' (only {len(text.split())} words of user-facing text). Spell checking requires at least 15 words of educational content."
        
        # Initialize spell checker with custom dictionary
        try:
            spell = SpellChecker()
            
            # Load custom Minecraft dictionary
            custom_dict = load_custom_dictionary()
            if custom_dict:
                spell.word_frequency.load_words(custom_dict)
                
        except Exception as e:
            return None, f"Error initializing spell checker: {str(e)}"
        
        # Clean text for spell checking - remove special characters but keep words
        try:
            cleaned_text = re.sub(r'[^\w\s\'-]', ' ', text)  # Keep apostrophes and hyphens
            words = cleaned_text.split()
            
            if not words:
                return None, f"No words found in the educational content after cleaning. Original text length: {len(text)}"
            
            # Filter out very short words and numbers
            words = [word for word in words if len(word) > 2 and not word.isdigit()]
            
            if not words:
                return None, f"No suitable words found for spell checking after filtering short words and numbers."
            
            # Remove duplicates while preserving order
            unique_words = []
            seen = set()
            for word in words:
                word_lower = word.lower()
                if word_lower not in seen:
                    unique_words.append(word)
                    seen.add(word_lower)
            
            if not unique_words:
                return None, f"No unique words found for spell checking."
                
        except Exception as e:
            return None, f"Error processing text for spell checking: {str(e)}"
        
        # Find misspelled words
        try:
            misspelled = spell.unknown(unique_words)
            if misspelled is None:
                misspelled = set()  # Ensure it's not None
        except Exception as e:
            return None, f"Error finding misspelled words: {str(e)}"
        
        # Generate suggestions for misspelled words
        spell_results = []
        try:
            for word in misspelled:
                try:
                    suggestions = spell.candidates(word)
                    if suggestions is None:
                        suggestions = []
                    else:
                        suggestions = list(suggestions)[:5]  # Top 5 suggestions
                except Exception as e:
                    print(f"Warning: Could not get suggestions for word '{word}': {str(e)}")
                    suggestions = []
                
                spell_results.append({
                    'word': word,
                    'suggestions': suggestions,
                    'context_usage': len([w for w in words if w.lower() == word.lower()])  # How many times it appears
                })
        except Exception as e:
            return None, f"Error generating spelling suggestions: {str(e)}"
        
        # Sort by usage frequency (most used misspellings first)
        spell_results.sort(key=lambda x: x['context_usage'], reverse=True)
        
        # Calculate statistics
        total_words = len(unique_words)
        misspelled_count = len(misspelled)
        accuracy_percentage = round(((total_words - misspelled_count) / max(total_words, 1)) * 100, 1)
        
        # Categorize errors
        common_errors = [result for result in spell_results if result['context_usage'] > 1]
        unique_errors = [result for result in spell_results if result['context_usage'] == 1]
        
        # Get custom dictionary info
        custom_dict_words = load_custom_dictionary()
        custom_words_used = [word for word in unique_words if word.lower() in custom_dict_words]
        
        # Create comprehensive results
        spell_check_results = {
            'analyzed_file': {
                'name': largest_file['name'],
                'path': largest_file['relative_path'],
                'size_kb': largest_file['size_kb'],
                'language_code': largest_file['language_code'],
                'is_english': largest_file['is_english'],
                'total_files_found': len(lang_files),
                'english_files_found': len(english_files),
                'non_english_files_found': len(non_english_files),
                'spell_check_note': spell_check_note
            },
            'statistics': {
                'total_unique_words': total_words,
                'misspelled_words': misspelled_count,
                'accuracy_percentage': accuracy_percentage,
                'extracted_text_length': len(text),
                'common_errors_count': len(common_errors),
                'unique_errors_count': len(unique_errors),
                'custom_dictionary_words': len(custom_dict_words),
                'custom_words_used_count': len(custom_words_used)
            },
            'errors': {
                'common_errors': common_errors,
                'unique_errors': unique_errors,
                'all_errors': spell_results
            },
            'quality_assessment': {
                'level': 'Excellent' if accuracy_percentage >= 95 else 
                        'Good' if accuracy_percentage >= 90 else 
                        'Fair' if accuracy_percentage >= 80 else 
                        'Needs Improvement',
                'description': get_spell_quality_description(accuracy_percentage, misspelled_count)
            }
        }
        
        return spell_check_results, None
        
    except FileNotFoundError:
        return None, "The unpacked world folder could not be found. Please ensure the world has been properly unpacked."
    except PermissionError:
        return None, "Permission denied when accessing language files. Please check file permissions."
    except Exception as e:
        return None, f"Error during spell checking: {str(e)}"

def get_spell_quality_description(accuracy_percentage, error_count):
    """Get a description of the spelling quality based on statistics"""
    if accuracy_percentage >= 95:
        return f"Excellent spelling quality with only {error_count} potential error(s). Content is professional and ready for educational use."
    elif accuracy_percentage >= 90:
        return f"Good spelling quality with {error_count} potential error(s). Minor review recommended before publication."
    elif accuracy_percentage >= 80:
        return f"Fair spelling quality with {error_count} potential error(s). Review and correction recommended for educational content."
    else:
        return f"Spelling needs improvement with {error_count} potential error(s). Comprehensive review required before educational use."

def load_custom_dictionary():
    """Load custom dictionary words from file"""
    try:
        custom_dict_path = os.path.join(app.config['UPLOAD_FOLDER'], 'custom_dictionary.txt')
        if os.path.exists(custom_dict_path):
            with open(custom_dict_path, 'r', encoding='utf-8') as f:
                words = [line.strip().lower() for line in f if line.strip()]
                return words
        else:
            # Create with default Minecraft terms
            create_default_custom_dictionary()
            return load_custom_dictionary()
    except Exception as e:
        print(f"Error loading custom dictionary: {e}")
        return []

def create_default_custom_dictionary():
    """Create default custom dictionary with common Minecraft terms"""
    default_words = [
        # Common Minecraft terms
        'minecraft', 'hotbar', 'toolbar', 'crafting', 'redstone', 'nether', 'enderdragon',
        'creeper', 'zombie', 'skeleton', 'enderman', 'villager', 'piglin', 'blaze',
        'overworld', 'stronghold', 'dungeon', 'mineshaft', 'ravine', 'bedrock',
        'obsidian', 'netherite', 'enchanting', 'brewing', 'potion', 'respawn',
        'gamemode', 'biome', 'savanna', 'taiga', 'tundra', 'mesa', 'swampland',
        'pickaxe', 'shovel', 'hoe', 'axe', 'sword', 'bow', 'crossbow', 'trident',
        'armor', 'helmet', 'chestplate', 'leggings', 'boots', 'shield',
        'cobblestone', 'sandstone', 'blackstone', 'deepslate', 'diorite', 'granite', 'andesite',
        'spawner', 'portal', 'beacon', 'hopper', 'dispenser', 'dropper', 'piston',
        'minecart', 'rail', 'boat', 'elytra', 'firework', 'rocket',
        # Education specific terms
        'npc', 'npcs', 'codebuild', 'codebuilder', 'classroom', 'worldbuilder',
        'immersive', 'edu', 'educational', 'tutorial', 'lesson', 'activity',
        'sustainability', 'biome', 'ecosystem', 'biodiversity'
    ]
    
    try:
        custom_dict_path = os.path.join(app.config['UPLOAD_FOLDER'], 'custom_dictionary.txt')
        with open(custom_dict_path, 'w', encoding='utf-8') as f:
            for word in default_words:
                f.write(f"{word.lower()}\n")
        print(f"Created default custom dictionary with {len(default_words)} words")
    except Exception as e:
        print(f"Error creating default custom dictionary: {e}")

def add_word_to_custom_dictionary(word):
    """Add a word to the custom dictionary"""
    try:
        word = word.lower().strip()
        if not word or len(word) < 2:
            return False, "Word must be at least 2 characters long"
        
        # Load existing words
        existing_words = load_custom_dictionary()
        
        if word in existing_words:
            return False, "Word already exists in custom dictionary"
        
        # Add the new word
        custom_dict_path = os.path.join(app.config['UPLOAD_FOLDER'], 'custom_dictionary.txt')
        with open(custom_dict_path, 'a', encoding='utf-8') as f:
            f.write(f"{word}\n")
        
        return True, f"Successfully added '{word}' to custom dictionary"
        
    except Exception as e:
        return False, f"Error adding word to dictionary: {str(e)}"

def get_custom_dictionary_words():
    """Get all words in the custom dictionary"""
    try:
        words = load_custom_dictionary()
        return sorted(words)
    except Exception as e:
        print(f"Error getting dictionary words: {e}")
        return []

def analyze_world_content(unpacked_folder_name):
    """Analyze world content to extract educational themes and information"""
    try:
        world_data = {}
        
        # Find and analyze language files
        lang_files = find_language_files(unpacked_folder_name)
        if lang_files:
            # Get the largest English file for analysis
            english_files = [f for f in lang_files if f['is_english']]
            if english_files:
                largest_file = max(english_files, key=lambda x: x['size_bytes'])
                educational_text = extract_text_from_lang_file(largest_file['full_path'])
                
                if educational_text:
                    world_data['educational_content'] = educational_text
                    world_data['primary_language_file'] = largest_file['name']
                    
                    # Extract themes and topics from content
                    world_data['themes'] = extract_educational_themes(educational_text)
                    world_data['key_concepts'] = extract_key_concepts(educational_text)
                    world_data['learning_objectives'] = generate_learning_objectives(educational_text)
        
        # Analyze world structure and files
        unpacked_path = os.path.join(app.config['UNPACKED_FOLDER'], unpacked_folder_name)
        world_data['world_info'] = analyze_world_structure(unpacked_path)
        
        return world_data
        
    except Exception as e:
        print(f"Error analyzing world content: {e}")
        return {}

def extract_educational_themes(text):
    """Extract main educational themes from text content"""
    themes = []
    
    # Define theme keywords and their associated themes
    theme_keywords = {
        'sustainability': ['sustainability', 'environment', 'green', 'renewable', 'conservation', 'recycle', 'eco'],
        'science': ['experiment', 'hypothesis', 'research', 'laboratory', 'scientific', 'discovery', 'analysis'],
        'history': ['historical', 'ancient', 'civilization', 'culture', 'heritage', 'timeline', 'era'],
        'geography': ['geography', 'climate', 'terrain', 'landscape', 'region', 'continent', 'natural'],
        'mathematics': ['mathematics', 'calculation', 'equation', 'geometry', 'measurement', 'statistics'],
        'technology': ['technology', 'innovation', 'engineering', 'digital', 'computer', 'automation'],
        'biology': ['biology', 'ecosystem', 'organism', 'species', 'habitat', 'biodiversity', 'life'],
        'chemistry': ['chemistry', 'chemical', 'reaction', 'compound', 'element', 'molecular'],
        'physics': ['physics', 'energy', 'force', 'motion', 'gravity', 'electricity', 'magnetism'],
        'social_studies': ['community', 'society', 'citizenship', 'government', 'democracy', 'rights'],
        'economics': ['economics', 'trade', 'business', 'market', 'economy', 'resource', 'production'],
        'art': ['art', 'creative', 'design', 'aesthetic', 'artistic', 'visual', 'cultural']
    }
    
    text_lower = text.lower()
    for theme, keywords in theme_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            themes.append(theme.replace('_', ' ').title())
    
    return themes[:5]  # Return top 5 themes

def extract_key_concepts(text):
    """Extract key concepts and vocabulary from educational text"""
    # Simple approach - extract longer phrases and important terms
    words = text.split()
    concepts = []
    
    # Look for capitalized terms (proper nouns, important concepts)
    for word in words:
        if len(word) > 3 and word[0].isupper() and word not in ['The', 'This', 'That', 'And', 'But', 'Or']:
            if word not in concepts:
                concepts.append(word)
    
    # Look for phrases that might be key concepts
    sentences = text.split('.')
    for sentence in sentences:
        if len(sentence.strip()) > 20 and len(sentence.strip()) < 100:
            # Extract noun phrases (simplified)
            words_in_sentence = sentence.strip().split()
            if len(words_in_sentence) > 2 and len(words_in_sentence) < 8:
                concept = sentence.strip()
                if concept not in concepts:
                    concepts.append(concept)
    
    return concepts[:10]  # Return top 10 key concepts

def generate_learning_objectives(text):
    """Generate learning objectives based on content analysis"""
    themes = extract_educational_themes(text)
    objectives = []
    
    # Base objectives templates for different themes
    objective_templates = {
        'Sustainability': [
            'Students will understand the importance of environmental conservation',
            'Students will identify renewable and non-renewable resources',
            'Students will analyze the impact of human activities on the environment'
        ],
        'Science': [
            'Students will apply the scientific method to investigate phenomena',
            'Students will analyze data and draw evidence-based conclusions',
            'Students will understand key scientific principles and concepts'
        ],
        'History': [
            'Students will analyze historical events and their significance',
            'Students will understand cause and effect relationships in history',
            'Students will compare different historical periods and cultures'
        ],
        'Geography': [
            'Students will identify and analyze geographic features and patterns',
            'Students will understand the relationship between humans and their environment',
            'Students will use geographic tools and technologies effectively'
        ]
    }
    
    # Generate objectives based on detected themes
    for theme in themes:
        if theme in objective_templates:
            objectives.extend(objective_templates[theme])
    
    # Add general objectives if no specific themes detected
    if not objectives:
        objectives = [
            'Students will engage with interactive educational content',
            'Students will develop problem-solving and critical thinking skills',
            'Students will collaborate effectively in a digital learning environment'
        ]
    
    return objectives[:6]  # Return up to 6 objectives

def analyze_world_structure(world_path):
    """Analyze world folder structure for additional educational context"""
    world_info = {
        'has_behavior_packs': False,
        'has_resource_packs': False,
        'has_structures': False,
        'estimated_age_range': 'Middle School (Ages 11-14)',
        'complexity_level': 'Intermediate'
    }
    
    try:
        if os.path.exists(os.path.join(world_path, 'behavior_packs')):
            world_info['has_behavior_packs'] = True
        if os.path.exists(os.path.join(world_path, 'resource_packs')):
            world_info['has_resource_packs'] = True
        if os.path.exists(os.path.join(world_path, 'structures')):
            world_info['has_structures'] = True
            
        # Determine complexity based on features
        complexity_score = 0
        if world_info['has_behavior_packs']:
            complexity_score += 2
        if world_info['has_resource_packs']:
            complexity_score += 1
        if world_info['has_structures']:
            complexity_score += 1
            
        if complexity_score >= 3:
            world_info['complexity_level'] = 'Advanced'
            world_info['estimated_age_range'] = 'High School (Ages 14-18)'
        elif complexity_score >= 1:
            world_info['complexity_level'] = 'Intermediate'
            world_info['estimated_age_range'] = 'Middle School (Ages 11-14)'
        else:
            world_info['complexity_level'] = 'Beginner'
            world_info['estimated_age_range'] = 'Elementary (Ages 8-11)'
            
    except Exception as e:
        print(f"Error analyzing world structure: {e}")
    
    return world_info

# AI-Enhanced Educational Resource Generation Functions

def get_largest_language_file_content(unpacked_folder_name):
    """Get the raw content from the largest language file in an unpacked world"""
    try:
        # Find all language files
        lang_files = find_language_files(unpacked_folder_name)
        
        if not lang_files:
            return None, "No language files found"
        
        # Prioritize English files, then fall back to largest file
        english_files = [f for f in lang_files if f.get('is_english', False)]
        
        if english_files:
            # Use the largest English file
            largest_file = max(english_files, key=lambda x: x.get('size_bytes', 0))
        else:
            # Use the largest file overall
            largest_file = max(lang_files, key=lambda x: x.get('size_bytes', 0))
        
        # Read the raw content without filtering
        try:
            with open(largest_file['full_path'], 'r', encoding='utf-8', errors='ignore') as f:
                raw_content = f.read()
        except:
            try:
                with open(largest_file['full_path'], 'r', encoding='latin-1', errors='ignore') as f:
                    raw_content = f.read()
            except:
                return None, f"Could not read file {largest_file['name']}"
        
        # Clean the content - remove comments and empty lines, but keep all key=value pairs
        cleaned_lines = []
        for line in raw_content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('//') and '=' in line:
                cleaned_lines.append(line)
        
        cleaned_content = '\n'.join(cleaned_lines)
        
        return {
            'content': cleaned_content,
            'raw_content': raw_content,
            'file_info': largest_file,
            'total_lines': len(cleaned_lines),
            'content_length': len(cleaned_content)
        }, None
        
    except Exception as e:
        return None, f"Error reading language file: {str(e)}"

def generate_ai_lesson_plan(world_data):
    """Generate an AI-powered lesson plan using Azure OpenAI GPT-5-Chat based on actual world content"""
    context = extract_educational_context(world_data)
    
    # Get the unpacked folder name from world_data
    unpacked_folder_name = world_data.get('unpacked_folder_name')
    
    # Try to get raw language file content first
    language_content = None
    content_source = "world analysis context"
    
    if unpacked_folder_name:
        try:
            lang_content_data, error = get_largest_language_file_content(unpacked_folder_name)
            if lang_content_data and not error:
                # Use raw language file content - strip down for AI processing
                raw_content = lang_content_data['content']
                
                # Clean and prepare content for AI - keep user-facing text
                content_lines = []
                for line in raw_content.split('\n'):
                    if '=' in line:
                        try:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Filter for user-facing content (similar to is_educational_content logic)
                            if value and len(value) > 5 and not value.startswith('minecraft:'):
                                # Include dialogue, messages, instructions, etc.
                                if any(pattern in key.lower() for pattern in [
                                    'dialog', 'message', 'text', 'instruction', 'guide', 'help',
                                    'npc', 'character', 'lesson', 'tutorial', 'story', 'narrative',
                                    'sign', 'book', 'chat', 'conversation', 'activity', 'quest'
                                ]):
                                    content_lines.append(f"{key}: {value}")
                        except ValueError:
                            continue
                
                if content_lines:
                    language_content = '\n'.join(content_lines[:50])  # Limit to 50 most relevant lines
                    content_source = f"raw content from {lang_content_data['file_info']['name']} ({lang_content_data['file_info']['language_code']})"
                    
        except Exception as e:
            print(f"Error getting language file content: {e}")
    
    # Fallback to extracted educational content or context
    if not language_content:
        educational_content = world_data.get('educational_content', '')
        
        if educational_content and len(educational_content.strip()) > 100:
            language_content = educational_content[:6000]  # Use extracted educational content
            content_source = "extracted educational text from language file analysis"
        else:
            # Build from context if no substantial content
            npc_dialogue_text = '\n'.join(context['npc_dialogue']) if context['npc_dialogue'] else 'No NPC dialogue found'
            learning_content_text = '\n'.join(context['learning_content']) if context['learning_content'] else 'No specific learning content found'
            language_content = f"NPC Dialogue:\n{npc_dialogue_text[:2000]}\n\nLearning Content:\n{learning_content_text[:2000]}"
            content_source = "extracted context from world analysis"
    
    key_concepts_text = ', '.join(context['key_concepts']) if context['key_concepts'] else 'General concepts'
    
    prompt = f"""
ANALYZE this Minecraft Education world and create a comprehensive lesson plan. First conduct a thorough educational analysis, then generate the lesson plan.

## WORLD METADATA:
- File Source: {context['world_name']} (technical filename)
- Target Age Range: {context['age_range']}
- Reading Level: {context['reading_level']}
- Complexity: {context['complexity_level']}
- Pre-identified Themes: {', '.join(context['themes']) if context['themes'] else 'Interactive Learning'}

## ACTUAL WORLD CONTENT TO ANALYZE ({content_source}):
{language_content}

## WORLD TECHNICAL FEATURES:
- Behavior Packs: {'Yes' if context['world_features']['has_behavior_packs'] else 'No'}
- Resource Packs: {'Yes' if context['world_features']['has_resource_packs'] else 'No'}
- Structures: {'Yes' if context['world_features']['has_structures'] else 'No'}

## KEY CONCEPTS IDENTIFIED: {key_concepts_text}

FIRST, analyze the world content above and determine:
1. What is the ACTUAL GAME TITLE? (Look in the content above for the real world/game title, not the filename)
2. What is the PRIMARY educational purpose of this world based on the actual content?
3. What specific learning outcomes can students achieve through this world?
4. What pedagogical approach does this world support (inquiry-based, problem-solving, simulation, etc.)?
5. How do the NPCs, dialogue, and world features support the learning objectives?
6. What real-world skills or knowledge does this world aim to develop?
7. What is the main storyline, scenario, or theme presented in the world content?

THEN, create a professional lesson plan document using this analysis:

# Educational Analysis and Lesson Plan: [Actual Game Title from Content]

## Educational Context Analysis

### Game Title and Theme
[The actual game title found in the content and its main theme/storyline]

### Primary Learning Purpose
[Based on world content analysis, what is the main educational goal?]

### Learning Outcomes
[What specific skills/knowledge will students gain?]

### Pedagogical Approach
[What teaching methodology does this world support?]

### World Design Evaluation
[How do the NPCs, dialogue, and features support learning?]

---

# Lesson Plan: [Specific Lesson Title Based on Actual Game Content]

## Learning Objectives
- [3-5 specific, measurable objectives based on your analysis above]

## Materials Needed
- Minecraft Education
- [Other specific materials based on world features]

## Lesson Structure

### Introduction (10 minutes)
- [Activities that leverage the world's specific context and purpose]

### Main Activity (25-35 minutes)
- [Step-by-step activities using identified NPCs, dialogue, and world mechanics]
- [Include specific references to world content found in the language files]

### Conclusion (10-15 minutes)
- [Synthesis activities connecting world experience to real-world applications]

## Assessment Methods
- [Evaluation strategies that align with the identified learning outcomes]

## Extension Activities
- [Additional activities building on the world's specific educational context]

## Real-World Connections
- [Specific connections to curriculum standards and life applications based on analysis]

## Implementation Notes
- [Specific guidance on using this world's unique features, NPCs, and content]

REQUIREMENTS:
- Base all content on the educational analysis conducted above
- Reference specific world elements (NPCs, dialogue, features) identified in the content
- Ensure activities match {context['age_range']} developmental needs
- Use professional document formatting
- NO conversational elements
"""

    ai_content = call_azure_openai(prompt, max_tokens=16384, temperature=0.7)
    
    if ai_content:
        return {
            'type': 'lesson_plan',
            'title': f"AI-Generated Lesson Plan: {context['world_name']}",
            'content': ai_content,
            'generated_by': 'Azure OpenAI GPT-5-Chat',
            'timestamp': datetime.now().isoformat(),
            'content_source': content_source,
            'content_length': len(language_content or '')
        }
    else:
        # No fallback - return error that AI is required
        return {
            'type': 'lesson_plan',
            'title': f"AI Lesson Plan Generation Unavailable",
            'content': "**AI Features Required**\n\nThis feature requires an active Azure OpenAI connection to generate AI-powered lesson plans. Please ensure your system administrator has configured the necessary AI credentials.\n\n**What this feature provides:**\n- Comprehensive lesson plans based on actual world content\n- Educational analysis of Minecraft Education worlds\n- Structured learning objectives and activities\n- Professional formatting with markdown support\n\nContact your administrator to enable AI features for the full educational resource generation experience.",
            'generated_by': 'System Message',
            'timestamp': datetime.now().isoformat(),
            'ai_unavailable': True
        }

def generate_ai_quiz(world_data):
    """Generate an AI-powered student quiz using Azure OpenAI GPT-5-Chat based on actual world content"""
    context = extract_educational_context(world_data)
    
    # Get the unpacked folder name from world_data
    unpacked_folder_name = world_data.get('unpacked_folder_name')
    
    # Try to get raw language file content first
    language_content = None
    content_source = "world analysis context"
    
    if unpacked_folder_name:
        try:
            lang_content_data, error = get_largest_language_file_content(unpacked_folder_name)
            if lang_content_data and not error:
                # Use raw language file content - strip down for AI processing
                raw_content = lang_content_data['content']
                
                # Clean and prepare content for AI - keep user-facing text
                content_lines = []
                for line in raw_content.split('\n'):
                    if '=' in line:
                        try:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Filter for user-facing content (similar to is_educational_content logic)
                            if value and len(value) > 5 and not value.startswith('minecraft:'):
                                # Include dialogue, messages, instructions, etc.
                                if any(pattern in key.lower() for pattern in [
                                    'dialog', 'message', 'text', 'instruction', 'guide', 'help',
                                    'npc', 'character', 'lesson', 'tutorial', 'story', 'narrative',
                                    'sign', 'book', 'chat', 'conversation', 'activity', 'quest'
                                ]):
                                    content_lines.append(f"{key}: {value}")
                        except ValueError:
                            continue
                
                if content_lines:
                    language_content = '\n'.join(content_lines[:50])  # Limit to 50 most relevant lines
                    content_source = f"raw content from {lang_content_data['file_info']['name']} ({lang_content_data['file_info']['language_code']})"
                    
        except Exception as e:
            print(f"Error getting language file content: {e}")
    
    # Fallback to extracted educational content or context
    if not language_content:
        educational_content = world_data.get('educational_content', '')
        
        if educational_content and len(educational_content.strip()) > 100:
            language_content = educational_content[:6000]  # Use extracted educational content
            content_source = "extracted educational text from language file analysis"
        else:
            # Build from context if no substantial content
            npc_dialogue_text = '\n'.join(context['npc_dialogue']) if context['npc_dialogue'] else 'No NPC dialogue found'
            learning_content_text = '\n'.join(context['learning_content']) if context['learning_content'] else 'No specific learning content found'
            language_content = f"NPC Dialogue:\n{npc_dialogue_text[:2000]}\n\nLearning Content:\n{learning_content_text[:2000]}"
            content_source = "extracted context from world analysis"
    
    key_concepts_text = ', '.join(context['key_concepts']) if context['key_concepts'] else 'General concepts'
    
    prompt = f"""
ANALYZE this Minecraft Education world and create a comprehensive student assessment quiz. First conduct a thorough educational analysis, then generate the quiz.

## WORLD METADATA:
- File Source: {context['world_name']} (technical filename)
- Target Age Range: {context['age_range']}
- Reading Level: {context['reading_level']}
- Complexity: {context['complexity_level']}
- Pre-identified Themes: {', '.join(context['themes']) if context['themes'] else 'Interactive Learning'}

## ACTUAL WORLD CONTENT TO ANALYZE ({content_source}):
{language_content}

## WORLD TECHNICAL FEATURES:
- Behavior Packs: {'Yes' if context['world_features']['has_behavior_packs'] else 'No'}
- Resource Packs: {'Yes' if context['world_features']['has_resource_packs'] else 'No'}
- Structures: {'Yes' if context['world_features']['has_structures'] else 'No'}

## KEY CONCEPTS IDENTIFIED: {key_concepts_text}

FIRST, analyze the world content above and determine:
1. What is the ACTUAL GAME TITLE? (Look in the content above for the real world/game title, not the filename)
2. What specific knowledge and skills does this world teach?
3. What are the key learning points students should demonstrate understanding of?
4. What types of assessment questions would best evaluate student comprehension?
5. How can quiz questions reference specific world elements (NPCs, scenarios, dialogue)?

THEN, create a professional student quiz document using this analysis:

# Student Assessment Quiz: [Actual Game Title from Content]

## Educational Context Analysis

### Game Title and Learning Focus
[The actual game title found in the content and what students are meant to learn]

### Assessment Objectives
[What knowledge/skills this quiz will evaluate based on the world content]

---

# Quiz: [Specific Quiz Title Based on Game Content]

## Instructions
[Clear instructions for students appropriate for {context['age_range']}]

## Section 1: Multiple Choice Questions
[5-7 multiple choice questions based on specific world content, NPCs, scenarios]

## Section 2: True/False Questions  
[3-5 true/false questions about key concepts from the world]

## Section 3: Short Answer Questions
[2-4 short answer questions requiring students to explain concepts or describe world elements]

## Section 4: Application Questions
[1-2 higher-order thinking questions connecting world learning to real-world applications]

## Answer Key
[Complete answer key with explanations referencing specific world content]

## Scoring Rubric
[Clear scoring guidelines appropriate for age group]

REQUIREMENTS:
- Base all questions on the actual world content and analysis above
- Reference specific NPCs, dialogue, scenarios, and world features in questions
- Make questions appropriate for {context['age_range']} cognitive level
- Use professional quiz formatting with clear sections
- Include varied question types to assess different learning levels
- NO conversational elements - direct educational content only
"""

    ai_content = call_azure_openai(prompt, max_tokens=16384, temperature=0.7)
    
    if ai_content:
        return {
            'type': 'student_quiz',
            'title': f"AI-Generated Quiz: {context['world_name']}",
            'content': ai_content,
            'generated_by': 'Azure OpenAI GPT-5-Chat',
            'timestamp': datetime.now().isoformat(),
            'content_source': content_source,
            'content_length': len(language_content or '')
        }
    else:
        # No fallback - return error that AI is required
        return {
            'type': 'student_quiz',
            'title': f"AI Quiz Generation Unavailable",
            'content': "**AI Features Required**\n\nThis feature requires an active Azure OpenAI connection to generate AI-powered student quizzes. Please ensure your system administrator has configured the necessary AI credentials.\n\n**What this feature provides:**\n- Comprehensive quizzes based on actual world content\n- Multiple question types (multiple-choice, short answer, critical thinking)\n- Age-appropriate questions aligned with learning objectives\n- Professional formatting with scoring rubrics\n- Content that references specific NPCs and world features\n\nContact your administrator to enable AI features for the full educational resource generation experience.",
            'generated_by': 'System Message',
            'timestamp': datetime.now().isoformat(),
            'ai_unavailable': True
        }

def generate_ai_parent_letter(world_data):
    """Generate an AI-powered parent letter using Azure OpenAI GPT-5-Chat based on actual world content"""
    context = extract_educational_context(world_data)
    
    # Get the unpacked folder name from world_data
    unpacked_folder_name = world_data.get('unpacked_folder_name')
    
    # Try to get raw language file content first
    language_content = None
    content_source = "world analysis context"
    
    if unpacked_folder_name:
        try:
            lang_content_data, error = get_largest_language_file_content(unpacked_folder_name)
            if lang_content_data and not error:
                # Use raw language file content - strip down for AI processing
                raw_content = lang_content_data['content']
                
                # Clean and prepare content for AI - keep user-facing text
                content_lines = []
                for line in raw_content.split('\n'):
                    if '=' in line:
                        try:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Filter for user-facing content (similar to is_educational_content logic)
                            if value and len(value) > 5 and not value.startswith('minecraft:'):
                                # Include dialogue, messages, instructions, etc.
                                if any(pattern in key.lower() for pattern in [
                                    'dialog', 'message', 'text', 'instruction', 'guide', 'help',
                                    'npc', 'character', 'lesson', 'tutorial', 'story', 'narrative',
                                    'sign', 'book', 'chat', 'conversation', 'activity', 'quest'
                                ]):
                                    content_lines.append(f"{key}: {value}")
                        except ValueError:
                            continue
                
                if content_lines:
                    language_content = '\n'.join(content_lines[:50])  # Limit to 50 most relevant lines
                    content_source = f"raw content from {lang_content_data['file_info']['name']} ({lang_content_data['file_info']['language_code']})"
                    
        except Exception as e:
            print(f"Error getting language file content: {e}")
    
    # Fallback to extracted educational content or context
    if not language_content:
        educational_content = world_data.get('educational_content', '')
        
        if educational_content and len(educational_content.strip()) > 100:
            language_content = educational_content[:6000]  # Use extracted educational content
            content_source = "extracted educational text from language file analysis"
        else:
            # Build from context if no substantial content
            npc_dialogue_text = '\n'.join(context['npc_dialogue']) if context['npc_dialogue'] else 'No NPC dialogue found'
            learning_content_text = '\n'.join(context['learning_content']) if context['learning_content'] else 'No specific learning content found'
            language_content = f"NPC Dialogue:\n{npc_dialogue_text[:2000]}\n\nLearning Content:\n{learning_content_text[:2000]}"
            content_source = "extracted context from world analysis"
    
    key_concepts_text = ', '.join(context['key_concepts']) if context['key_concepts'] else 'General concepts'
    
    prompt = f"""
ANALYZE this Minecraft Education world and create a comprehensive parent information letter. First conduct a thorough educational analysis, then generate the parent communication.

## WORLD METADATA:
- File Source: {context['world_name']} (technical filename)
- Target Age Range: {context['age_range']}
- Reading Level: {context['reading_level']}
- Complexity: {context['complexity_level']}
- Pre-identified Themes: {', '.join(context['themes']) if context['themes'] else 'Interactive Learning'}

## ACTUAL WORLD CONTENT TO ANALYZE ({content_source}):
{language_content}

## WORLD TECHNICAL FEATURES:
- Behavior Packs: {'Yes' if context['world_features']['has_behavior_packs'] else 'No'}
- Resource Packs: {'Yes' if context['world_features']['has_resource_packs'] else 'No'}
- Structures: {'Yes' if context['world_features']['has_structures'] else 'No'}

## KEY CONCEPTS IDENTIFIED: {key_concepts_text}

FIRST, analyze the world content above and determine:
1. What is the ACTUAL GAME TITLE? (Look in the content above for the real world/game title, not the filename)
2. What specific educational benefits will students gain from this world?
3. What skills (21st century skills, curriculum standards) does this world develop?
4. What might parents be curious or concerned about regarding their child's Minecraft education?
5. How can parents support this learning at home?
6. What makes this particular world educationally valuable?

THEN, create a professional parent communication letter using this analysis. Start directly with the letter - no analysis section:

# Dear Parents and Guardians,

## Re: Upcoming Minecraft Education Activity - [Actual Game Title]

[Professional, warm introduction explaining the upcoming Minecraft Education activity using the actual game title]

## About This Educational Experience

[Detailed explanation of what this specific world teaches, based on actual content analysis]

## Educational Benefits for Your Child

### Academic Skills Development
[Specific academic skills this world develops, appropriate for {context['age_range']}]

### 21st Century Skills
[Critical thinking, collaboration, creativity, communication skills this world fosters]

### Curriculum Connections
[How this world aligns with curriculum standards and learning objectives]

## What Your Child Will Experience

[Specific activities, challenges, and learning experiences based on world content analysis]

## Safety and Digital Citizenship

[Information about Minecraft Education's safety features and supervised learning environment]

## How You Can Support Learning at Home

[Specific suggestions for extending world-based learning into home conversations and activities]

## Addressing Common Parent Questions

### Is this just playing games?
[Professional explanation of educational gaming and learning through play]

### What about screen time concerns?
[Balanced perspective on educational screen time vs entertainment screen time]

### How does this connect to "real" learning?
[Specific examples of how world skills transfer to academic and life success]

## Contact Information

[Teacher contact information and invitation for questions or concerns]

## Conclusion

[Positive closing emphasizing partnership in child's education]

Sincerely,
[Teacher Name]
[School/Class Information]

REQUIREMENTS:
- Base all content on the educational analysis conducted above
- Reference specific world elements and learning opportunities identified in the content
- Use warm, professional tone appropriate for parent communication
- Address common parent concerns about gaming in education
- Make content specific to THIS world, not generic Minecraft education
- Use clear, accessible language that explains educational benefits
- NO conversational elements - direct professional communication only
"""

    ai_content = call_azure_openai(prompt, max_tokens=16384, temperature=0.7)
    
    if ai_content:
        return {
            'type': 'parent_letter',
            'title': f"Parent Letter: {context['world_name']}",
            'content': ai_content,
            'generated_by': 'Azure OpenAI GPT-5-Chat',
            'timestamp': datetime.now().isoformat(),
            'content_source': content_source,
            'content_length': len(language_content or '')
        }
    else:
        # No fallback - return error that AI is required
        return {
            'type': 'parent_letter',
            'title': f"AI Parent Letter Generation Unavailable",
            'content': "**AI Features Required**\n\nThis feature requires an active Azure OpenAI connection to generate AI-powered parent letters. Please ensure your system administrator has configured the necessary AI credentials.\n\n**What this feature provides:**\n- Personalized parent letters based on specific world content\n- Educational explanations of learning objectives\n- Professional communication addressing gaming in education\n- Specific references to world activities and NPCs\n- Age-appropriate educational context and benefits\n\nContact your administrator to enable AI features for the full educational resource generation experience.",
            'generated_by': 'System Message',
            'timestamp': datetime.now().isoformat(),
            'ai_unavailable': True
        }

def generate_educational_resource(unpacked_folder_name, resource_type):
    """Generate a specific type of educational resource"""
    try:
        print(f"Generating {resource_type} for {unpacked_folder_name}")
        
        # Analyze world content first
        world_data = analyze_world_content(unpacked_folder_name)
        
        if not world_data:
            print("World data analysis returned None")
            return None
        
        print(f"World data analyzed successfully, keys: {list(world_data.keys())}")
        
        # Add the unpacked folder name to world_data for AI functions
        world_data['unpacked_folder_name'] = unpacked_folder_name
            
        # Generate resource based on type using AI-enhanced versions
        if resource_type == 'lesson_plan':
            print("Calling generate_ai_lesson_plan")
            result = generate_ai_lesson_plan(world_data)
            print(f"AI lesson plan result: {'Success' if result else 'Failed'}")
            return result
        elif resource_type == 'student_quiz':
            print("Calling generate_ai_quiz")
            result = generate_ai_quiz(world_data)
            print(f"AI quiz result: {'Success' if result else 'Failed'}")
            return result
        elif resource_type == 'topic_introduction':
            return generate_topic_introduction(world_data)
        elif resource_type == 'parent_letter':
            print("Calling generate_ai_parent_letter")
            result = generate_ai_parent_letter(world_data)
            print(f"AI parent letter result: {'Success' if result else 'Failed'}")
            return result
        else:
            print(f"Unknown resource type: {resource_type}")
            return None
            
    except Exception as e:
        print(f"Error generating educational resource: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return None

def generate_lesson_plan(world_data):
    """Generate a comprehensive lesson plan"""
    themes = world_data.get('themes', ['Interactive Learning'])
    objectives = world_data.get('learning_objectives', [])
    world_info = world_data.get('world_info', {})
    
    lesson_plan = {
        'title': f"Minecraft Education Lesson: {themes[0] if themes else 'Interactive Learning'}",
        'grade_level': world_info.get('estimated_age_range', 'Middle School (Ages 11-14)'),
        'duration': '45-60 minutes',
        'subject_areas': themes,
        'learning_objectives': objectives,
        'materials_needed': [
            'Minecraft Education',
            'Student devices (tablets/computers)',
            'World file: ' + world_data.get('primary_language_file', 'Educational World'),
            'Student worksheets (optional)',
            'Projector/Smart Board for demonstrations'
        ],
        'lesson_structure': {
            'introduction': {
                'time': '10 minutes',
                'activities': [
                    'Welcome students and introduce the lesson topic',
                    'Review learning objectives and expectations',
                    'Demonstrate basic Minecraft Education controls if needed',
                    'Explain the virtual world they will be exploring'
                ]
            },
            'main_activity': {
                'time': '25-35 minutes',
                'activities': [
                    'Students load the educational world',
                    'Guide students through key learning areas',
                    'Encourage exploration and interaction with educational content',
                    'Facilitate collaborative problem-solving activities',
                    'Monitor student progress and provide assistance as needed'
                ]
            },
            'conclusion': {
                'time': '10-15 minutes',
                'activities': [
                    'Students share discoveries and insights',
                    'Review key concepts learned during the session',
                    'Connect virtual learning to real-world applications',
                    'Assign follow-up activities or homework if applicable'
                ]
            }
        },
        'assessment_strategies': [
            'Observe student engagement and participation',
            'Review student responses to in-world activities',
            'Conduct exit ticket or quick quiz on key concepts',
            'Evaluate collaborative skills and teamwork'
        ],
        'extension_activities': [
            'Research project on lesson themes',
            'Create presentation about discoveries made in the world',
            'Design own Minecraft structures related to the topic',
            'Write reflection journal about the learning experience'
        ],
        'differentiation': [
            'Pair struggling students with more experienced players',
            'Provide additional time for students who need it',
            'Offer advanced challenges for quick finishers',
            'Use visual and auditory cues for different learning styles'
        ]
    }
    
    return lesson_plan

def generate_student_quiz(world_data):
    """Generate a student quiz based on world content"""
    themes = world_data.get('themes', ['Interactive Learning'])
    key_concepts = world_data.get('key_concepts', [])
    educational_content = world_data.get('educational_content', '')
    
    quiz = {
        'title': f"Quiz: {themes[0] if themes else 'Interactive Learning'} in Minecraft",
        'instructions': 'Answer the following questions based on your exploration of the Minecraft Education world.',
        'questions': []
    }
    
    # Generate different types of questions
    questions = []
    
    # Multiple choice questions based on themes
    if 'Sustainability' in themes:
        questions.extend([
            {
                'type': 'multiple_choice',
                'question': 'What is the most important benefit of renewable energy sources?',
                'options': [
                    'They are cheaper to build',
                    'They do not run out over time',
                    'They are easier to transport',
                    'They work in all weather conditions'
                ],
                'correct_answer': 1,
                'explanation': 'Renewable energy sources like solar and wind do not run out over time, unlike fossil fuels.'
            },
            {
                'type': 'multiple_choice',
                'question': 'Which of these activities helps reduce waste?',
                'options': [
                    'Buying more products',
                    'Recycling materials',
                    'Using disposable items',
                    'Throwing everything away'
                ],
                'correct_answer': 1,
                'explanation': 'Recycling materials helps reduce waste by giving materials a second life.'
            }
        ])
    
    if 'Science' in themes:
        questions.extend([
            {
                'type': 'multiple_choice',
                'question': 'What is the first step in the scientific method?',
                'options': [
                    'Conduct an experiment',
                    'Make an observation',
                    'Form a conclusion',
                    'Analyze data'
                ],
                'correct_answer': 1,
                'explanation': 'The scientific method begins with making an observation about the world around us.'
            }
        ])
    
    # True/False questions
    questions.extend([
        {
            'type': 'true_false',
            'question': 'Minecraft Education can be used to learn about real-world concepts.',
            'correct_answer': True,
            'explanation': 'Minecraft Education is specifically designed to teach real-world concepts through virtual exploration.'
        },
        {
            'type': 'true_false',
            'question': 'Working together in Minecraft Education is discouraged.',
            'correct_answer': False,
            'explanation': 'Collaboration and teamwork are encouraged in Minecraft Education to enhance learning.'
        }
    ])
    
    # Short answer questions based on content
    if key_concepts:
        questions.append({
            'type': 'short_answer',
            'question': f'Explain what you learned about {key_concepts[0] if key_concepts else "the main topic"} in the Minecraft world.',
            'sample_answer': f'Students should demonstrate understanding of {key_concepts[0] if key_concepts else "the main topic"} through specific examples from their virtual exploration.',
            'points': 5
        })
    
    questions.append({
        'type': 'short_answer',
        'question': 'Describe one way the concepts you learned in Minecraft could be applied in the real world.',
        'sample_answer': 'Students should connect virtual learning to real-world applications, showing critical thinking skills.',
        'points': 5
    })
    
    # Essay question
    questions.append({
        'type': 'essay',
        'question': f'Write a paragraph explaining how your experience in the Minecraft Education world helped you understand {themes[0] if themes else "the subject matter"} better. Include specific examples from your exploration.',
        'rubric': {
            'content': 'Demonstrates clear understanding of subject matter (4 points)',
            'examples': 'Uses specific examples from Minecraft experience (3 points)',
            'writing': 'Clear, organized writing with proper grammar (3 points)'
        },
        'total_points': 10
    })
    
    quiz['questions'] = questions[:8]  # Limit to 8 questions for reasonable length
    quiz['total_points'] = sum(q.get('points', 1) for q in quiz['questions'])
    
    return quiz

def generate_topic_introduction(world_data):
    """Generate an introduction to the topic/theme"""
    themes = world_data.get('themes', ['Interactive Learning'])
    world_info = world_data.get('world_info', {})
    key_concepts = world_data.get('key_concepts', [])
    
    primary_theme = themes[0] if themes else 'Interactive Learning'
    
    introduction = {
        'title': f'Introduction to {primary_theme}',
        'overview': f'Welcome to an exciting journey into {primary_theme.lower()}! Through this interactive Minecraft Education experience, you will explore, discover, and learn about important concepts in a virtual world designed specifically for education.',
        'what_you_will_learn': [
            f'Key principles and concepts related to {primary_theme.lower()}',
            'Real-world applications and examples',
            'Problem-solving skills through hands-on activities',
            'Collaboration and teamwork in a digital environment'
        ],
        'why_this_matters': f'{primary_theme} is an important subject that affects our daily lives and future. By understanding these concepts, you will be better prepared to make informed decisions and contribute positively to society.',
        'key_vocabulary': key_concepts[:8] if key_concepts else [
            'Interactive Learning', 'Virtual Environment', 'Educational Content', 'Collaboration'
        ],
        'getting_started': [
            'Launch Minecraft Education on your device',
            'Join the educational world with your classmates',
            'Follow the guided tour to familiarize yourself with the environment',
            'Pay attention to signs, NPCs, and interactive elements',
            'Work together with your peers to complete activities',
            'Ask questions and explore beyond the basic requirements'
        ],
        'learning_tips': [
            'Take your time to read all informational content',
            'Experiment with different approaches to problems',
            'Discuss your findings with classmates',
            'Connect what you see in Minecraft to the real world',
            'Keep notes of important discoveries',
            'Don\'t be afraid to explore and try new things'
        ],
        'success_indicators': [
            'You can explain key concepts in your own words',
            'You can provide real-world examples of the concepts',
            'You actively participate in group activities',
            'You ask thoughtful questions about the subject matter',
            'You make connections between virtual and real experiences'
        ]
    }
    
    return introduction

def generate_parent_letter(world_data):
    """Generate a letter for parents introducing the educational game"""
    themes = world_data.get('themes', ['Interactive Learning'])
    world_info = world_data.get('world_info', {})
    primary_theme = themes[0] if themes else 'Interactive Learning'
    
    letter = {
        'subject': f'Your Child Will Be Learning About {primary_theme} Through Minecraft Education',
        'greeting': 'Dear Parents and Guardians,',
        'introduction': f'I am excited to share with you an innovative learning opportunity that your child will be participating in. We will be using Minecraft Education to explore and learn about {primary_theme.lower()} in an engaging, interactive virtual environment.',
        'about_minecraft_education': {
            'title': 'What is Minecraft Education?',
            'content': 'Minecraft Education is a game-based learning platform that promotes creativity, collaboration, and problem-solving in an immersive digital environment. It is specifically designed for educational use and is used by millions of students worldwide to learn subjects ranging from history and science to mathematics and language arts.'
        },
        'learning_benefits': {
            'title': f'How Will This Help Your Child Learn About {primary_theme}?',
            'benefits': [
                'Engages students through interactive, hands-on exploration',
                'Promotes collaboration and teamwork skills',
                'Develops problem-solving and critical thinking abilities',
                'Makes abstract concepts tangible and understandable',
                'Accommodates different learning styles and paces',
                'Connects virtual learning to real-world applications'
            ]
        },
        'what_to_expect': {
            'title': 'What Your Child Will Be Doing',
            'activities': [
                f'Exploring a specially designed virtual world focused on {primary_theme.lower()}',
                'Participating in guided activities and challenges',
                'Collaborating with classmates to solve problems',
                'Interacting with educational content and characters',
                'Completing assignments that reinforce learning objectives',
                'Presenting findings and sharing discoveries with the class'
            ]
        },
        'safety_and_monitoring': {
            'title': 'Safety and Supervision',
            'content': 'Minecraft Education provides a safe, controlled environment for learning. Students can only interact with their classmates, and all activities are supervised by the teacher. The platform includes built-in tools for classroom management and student monitoring.'
        },
        'support_at_home': {
            'title': 'How You Can Support Learning at Home',
            'suggestions': [
                f'Ask your child about what they learned regarding {primary_theme.lower()}',
                'Encourage them to share their discoveries and experiences',
                f'Look for real-world examples of {primary_theme.lower()} concepts together',
                'Support any homework or extension activities assigned',
                'Show interest in their virtual creations and achievements',
                'Discuss how the lesson connects to current events or daily life'
            ]
        },
        'addressing_concerns': {
            'title': 'Common Questions and Concerns',
            'qa': [
                {
                    'question': 'Is this just playing games instead of learning?',
                    'answer': 'No, this is purposeful, curriculum-aligned learning that happens to use a game-based platform. Studies show that game-based learning can improve engagement and retention of educational content.'
                },
                {
                    'question': 'Will my child become too focused on gaming?',
            'answer': 'Minecraft Education is different from recreational gaming. It is used as a learning tool with specific educational objectives and time limits.'
                },
                {
                    'question': 'What if my child is not familiar with Minecraft?',
                    'answer': 'No prior experience is necessary. We will provide instruction on the basic controls and navigation. Many students actually learn these skills quickly.'
                }
            ]
        },
        'contact_information': {
            'title': 'Questions or Concerns?',
            'content': 'If you have any questions about this learning activity or would like to discuss your child\'s progress, please don\'t hesitate to reach out to me. I am committed to ensuring that every student has a positive and educational experience.'
        },
        'closing': 'I look forward to sharing your child\'s learning journey and discoveries with you. Thank you for your continued support of innovative educational approaches.',
        'signature': 'Sincerely,\n[Teacher Name]\n[Subject/Grade Level]\n[School Name]\n[Contact Information]'
    }
    
    return letter

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

@app.route('/admin')
@login_required
def admin_panel():
    """Admin panel for account management"""
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    users_data = get_users_data()
    users_list = []
    
    for username, user_data in users_data.items():
        # Count user's worlds and unpacked worlds
        metadata = load_metadata()
        unpacked_metadata = load_unpacked_metadata()
        
        user_worlds = len([w for w in metadata if w.get('uploaded_by') == username])
        user_unpacked = len([u for u in unpacked_metadata if u.get('unpacked_by') == username])
        
        users_list.append({
            'username': username,
            'id': user_data['id'],
            'first_name': user_data.get('first_name', ''),
            'surname': user_data.get('surname', ''),
            'email': user_data.get('email', ''),
            'full_name': f"{user_data.get('first_name', '')} {user_data.get('surname', '')}".strip(),
            'is_admin': user_data.get('is_admin', False),
            'created_date': user_data.get('created_date', 'N/A'),
            'worlds_count': user_worlds,
            'unpacked_count': user_unpacked
        })
    
    # Sort by creation date (newest first)
    users_list.sort(key=lambda x: x['created_date'], reverse=True)
    
    return render_template('admin_panel.html', 
                         user=current_user, 
                         users=users_list,
                         ai_features_available=AI_FEATURES_AVAILABLE,
                         ai_status_message=AI_STATUS_MESSAGE)

@app.route('/admin/create_user', methods=['POST'])
@login_required
def admin_create_user():
    """Create a new user account"""
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    first_name = request.form.get('first_name', '').strip()
    surname = request.form.get('surname', '').strip()
    email = request.form.get('email', '').strip()
    is_admin_user = request.form.get('is_admin') == 'on'
    
    # Validation
    if not all([username, password, first_name, surname, email]):
        flash('All fields are required.', 'error')
        return redirect(url_for('admin_panel'))
    
    if len(username) < 3:
        flash('Username must be at least 3 characters long.', 'error')
        return redirect(url_for('admin_panel'))
    
    if len(password) < 6:
        flash('Password must be at least 6 characters long.', 'error')
        return redirect(url_for('admin_panel'))
    
    if len(first_name) < 2:
        flash('First name must be at least 2 characters long.', 'error')
        return redirect(url_for('admin_panel'))
    
    if len(surname) < 2:
        flash('Surname must be at least 2 characters long.', 'error')
        return redirect(url_for('admin_panel'))
    
    # Basic email validation
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        flash('Please enter a valid email address.', 'error')
        return redirect(url_for('admin_panel'))
    
    # Check for invalid characters in username
    if not username.replace('_', '').replace('-', '').isalnum():
        flash('Username can only contain letters, numbers, hyphens, and underscores.', 'error')
        return redirect(url_for('admin_panel'))
    
    success, message = create_user(username, password, first_name, surname, email, is_admin_user)
    
    if success:
        # Reload users to include the new user
        global users
        users = load_users()
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_user/<username>')
@login_required
def admin_delete_user(username):
    """Delete a user account and all associated data"""
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    if username == current_user.username:
        flash('Cannot delete your own account.', 'error')
        return redirect(url_for('admin_panel'))
    
    success, message = delete_user_and_data(username)
    
    if success:
        # Reload users to reflect the deletion
        global users
        users = load_users()
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/ai_config', methods=['GET', 'POST'])
@login_required
def admin_ai_config():
    """Admin AI Configuration Management"""
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # Get form data
        api_key = request.form.get('api_key', '').strip()
        endpoint = request.form.get('endpoint', '').strip()
        deployment_name = request.form.get('deployment_name', '').strip()
        api_version = request.form.get('api_version', '').strip()
        
        # Validate required fields
        if not api_key or not endpoint:
            flash('API Key and Endpoint are required fields.', 'error')
            return redirect(url_for('admin_ai_config'))
        
        # Set defaults if not provided
        if not deployment_name:
            deployment_name = 'gpt-5-chat'
        if not api_version:
            api_version = '2024-12-01-preview'
        
        try:
            # Read existing .env or create new content
            env_path = '.env'
            env_content = {}
            
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_content[key.strip()] = value.strip()
            
            # Update AI configuration
            env_content['AZURE_OPENAI_API_KEY'] = api_key
            env_content['AZURE_OPENAI_ENDPOINT'] = endpoint
            env_content['AZURE_OPENAI_DEPLOYMENT_NAME'] = deployment_name
            env_content['AZURE_OPENAI_API_VERSION'] = api_version
            
            # Write back to .env file
            with open(env_path, 'w') as f:
                for key, value in env_content.items():
                    f.write(f"{key}={value}\n")
            
            flash('AI configuration saved successfully! Restart the application to apply changes.', 'success')
            
        except Exception as e:
            flash(f'Error saving AI configuration: {str(e)}', 'error')
        
        return redirect(url_for('admin_ai_config'))
    
    # GET request - show current configuration
    current_config = {
        'api_key': AZURE_OPENAI_API_KEY or '',
        'endpoint': AZURE_OPENAI_ENDPOINT or '',
        'deployment_name': AZURE_OPENAI_DEPLOYMENT_NAME or 'gpt-5-chat',
        'api_version': AZURE_OPENAI_API_VERSION or '2024-12-01-preview',
        'ai_available': AI_FEATURES_AVAILABLE,
        'ai_status': AI_STATUS_MESSAGE
    }
    
    return render_template('admin_ai_config.html', user=current_user, config=current_config)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request (placeholder for future implementation)"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')
        
        # Check if email exists
        users_data = get_users_data()
        user_found = False
        for user_data in users_data.values():
            if user_data.get('email', '').lower() == email:
                user_found = True
                break
        
        # Always show success message for security (don't reveal if email exists)
        flash('If your email address is registered, you will receive password reset instructions shortly.', 'info')
        
        # TODO: Implement actual email sending functionality here
        # For now, just log the request
        if user_found:
            print(f"Password reset requested for email: {email}")
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

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

@app.route('/spell_check/<int:unpacked_id>')
@login_required
def spell_check_route(unpacked_id):
    """Perform spell checking on the largest English .lang file in an unpacked world"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404
    
    try:
        spell_results, error = perform_spell_check(world['folder_name'])
        
        if error:
            return jsonify({'error': error}), 400
        
        if not spell_results:
            return jsonify({'error': 'Spell checking failed'}), 500
        
        return jsonify({
            'success': True,
            'world': world,
            'spell_check': spell_results
        })
        
    except Exception as e:
        return jsonify({'error': f'Error during spell checking: {str(e)}'}), 500

@app.route('/add_to_dictionary', methods=['POST'])
@login_required
def add_to_dictionary():
    """Add a word to the custom dictionary"""
    try:
        data = request.get_json()
        if not data or 'word' not in data:
            return jsonify({'error': 'No word provided'}), 400
        
        word = data['word']
        success, message = add_word_to_custom_dictionary(word)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'word': word
            })
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        return jsonify({'error': f'Error adding word to dictionary: {str(e)}'}), 500

@app.route('/get_custom_dictionary')
@login_required
def get_custom_dictionary():
    """Get all words in the custom dictionary"""  
    try:
        words = get_custom_dictionary_words()
        return jsonify({
            'success': True,
            'words': words,
            'count': len(words)
        })
    except Exception as e:
        return jsonify({'error': f'Error getting custom dictionary: {str(e)}'}), 500

@app.route('/educational_resources')
@login_required
def educational_resources():
    """Educational resources main page - shows list of unpacked worlds"""
    unpacked_worlds = load_unpacked_metadata()
    unpacked_worlds.sort(key=lambda x: x['unpacked_date'], reverse=True)
    return render_template('educational_resources_list.html', user=current_user, unpacked_worlds=unpacked_worlds)

@app.route('/educational_resources/<int:unpacked_id>')
@login_required
def educational_resources_world(unpacked_id):
    """Educational resources page for a specific unpacked world"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('educational_resources'))
    
    return render_template('educational_resources_world.html', user=current_user, world=world)

@app.route('/generate_resource/<int:unpacked_id>/<resource_type>')
@login_required
def generate_resource(unpacked_id, resource_type):
    """Generate a specific educational resource"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404

    try:
        # Generate the requested resource
        resource_data = generate_educational_resource(world['folder_name'], resource_type)
        
        if not resource_data:
            return jsonify({'error': f'Could not generate {resource_type}'}), 400
        
        return jsonify({
            'success': True,
            'resource_type': resource_type,
            'data': resource_data
        })
        
    except Exception as e:
        return jsonify({'error': f'Error generating {resource_type}: {str(e)}'}), 500

@app.route('/language_file_editor/<int:unpacked_id>')
@login_required
def language_file_editor(unpacked_id):
    """Language file editor file selection page"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('language_tools'))
    
    return render_template('language_file_selector.html', user=current_user, world=world)

@app.route('/language_file_editor/<int:unpacked_id>/edit')
@login_required
def edit_language_file(unpacked_id):
    """Language file editor for editing a specific file"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        flash('Unpacked world not found', 'error')
        return redirect(url_for('language_tools'))
    
    file_path = request.args.get('file_path')
    if not file_path:
        flash('No file specified', 'error')
        return redirect(url_for('language_file_editor', unpacked_id=unpacked_id))
    
    return render_template('language_file_editor.html', user=current_user, world=world, file_path=file_path)

@app.route('/api/get_language_files/<int:unpacked_id>')
@login_required
def api_get_language_files(unpacked_id):
    """API endpoint to get language files for editor"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404
    
    try:
        # Find language files
        lang_files = find_language_files(world['folder_name'])
        
        return jsonify({
            'success': True,
            'language_files': lang_files
        })
        
    except Exception as e:
        return jsonify({'error': f'Error finding language files: {str(e)}'}), 500

@app.route('/api/get_file_content/<int:unpacked_id>')
@login_required
def api_get_file_content(unpacked_id):
    """API endpoint to get content of a specific language file"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404
    
    file_path = request.args.get('file_path')
    if not file_path:
        return jsonify({'error': 'File path is required'}), 400
    
    try:
        # Construct full path to the file
        unpacked_folder = os.path.join(app.config['UNPACKED_FOLDER'], world['folder_name'])
        full_file_path = os.path.join(unpacked_folder, file_path)
        
        # Security check - ensure file is within the unpacked folder
        if not os.path.abspath(full_file_path).startswith(os.path.abspath(unpacked_folder)):
            return jsonify({'error': 'Invalid file path'}), 400
        
        # Check if file exists
        if not os.path.exists(full_file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Read file content
        try:
            with open(full_file_path, 'r', encoding='utf-8') as file:
                content = file.read()
        except UnicodeDecodeError:
            # Try with different encoding if UTF-8 fails
            with open(full_file_path, 'r', encoding='latin-1') as file:
                content = file.read()
        
        return jsonify({
            'success': True,
            'content': content,
            'file_path': file_path,
            'file_name': os.path.basename(file_path)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error reading file: {str(e)}'}), 500

@app.route('/api/save_file_content/<int:unpacked_id>', methods=['POST'])
@login_required
def api_save_file_content(unpacked_id):
    """API endpoint to save content to a language file"""
    world = get_unpacked_world_by_id(unpacked_id)
    if not world:
        return jsonify({'error': 'Unpacked world not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    file_path = data.get('file_path')
    content = data.get('content')
    
    if not file_path or content is None:
        return jsonify({'error': 'File path and content are required'}), 400
    
    try:
        # Construct full path to the file
        unpacked_folder = os.path.join(app.config['UNPACKED_FOLDER'], world['folder_name'])
        full_file_path = os.path.join(unpacked_folder, file_path)
        
        # Security check - ensure file is within the unpacked folder
        if not os.path.abspath(full_file_path).startswith(os.path.abspath(unpacked_folder)):
            return jsonify({'error': 'Invalid file path'}), 400
        
        # Create backup of original file
        backup_path = full_file_path + '.backup'
        if os.path.exists(full_file_path):
            shutil.copy2(full_file_path, backup_path)
        
        # Write new content
        with open(full_file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        
        return jsonify({
            'success': True,
            'message': 'File saved successfully',
            'backup_created': os.path.exists(backup_path)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error saving file: {str(e)}'}), 500

@app.route('/api/spell_check_content', methods=['POST'])
@login_required
def api_spell_check_content():
    """API endpoint to spell check text content"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    content = data.get('content')
    if not content:
        return jsonify({'error': 'Content is required'}), 400
    
    try:
        # Ensure NLTK data is available
        try:
            import nltk
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            try:
                nltk.download('punkt', quiet=True)
            except:
                try:
                    nltk.download('punkt_tab', quiet=True)
                except:
                    pass
        
        # Initialize spell checker with custom dictionary
        spell = SpellChecker()
        
        # Load custom dictionary if it exists
        custom_dict_path = 'custom_dictionary.txt'
        if os.path.exists(custom_dict_path):
            with open(custom_dict_path, 'r', encoding='utf-8') as f:
                custom_words = [word.strip().lower() for word in f.readlines() if word.strip()]
                spell.word_frequency.load_words(custom_words)
        
        # Extract text from language file format (only values after =)
        educational_text = ""
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
            
            if '=' in line:
                # Extract key and value parts
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Filter for educational content
                if is_educational_content(key, value):
                    educational_text += f"LINE_{line_num}: {value}\n"
        
        if not educational_text:
            return jsonify({
                'success': True,
                'errors': [],
                'total_words': 0,
                'misspelled_words': 0
            })
        
        # Check spelling
        words = nltk.word_tokenize(educational_text.lower())
        if words is None:
            words = []
        # Filter out non-alphabetic words and punctuation
        words = [word for word in words if word.isalpha() and len(word) > 1]
        
        # Find misspelled words
        misspelled = spell.unknown(words)
        if misspelled is None:
            misspelled = set()
        
        # Get line-specific errors
        errors_by_line = {}
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
                
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if is_educational_content(key, value):
                    line_words = nltk.word_tokenize(value.lower())
                    if line_words is None:
                        line_words = []
                    line_words = [word for word in line_words if word.isalpha() and len(word) > 1]
                    line_misspelled = [word for word in line_words if word in misspelled]
                    
                    if line_misspelled:
                        suggestions = {}
                        for word in line_misspelled:
                            candidates = spell.candidates(word)
                            if candidates:
                                suggestions[word] = list(candidates)[:3]
                            else:
                                suggestions[word] = []
                        
                        errors_by_line[line_num] = {
                            'line_number': line_num,
                            'line_text': line,
                            'misspelled_words': line_misspelled,
                            'suggestions': suggestions
                        }
        
        return jsonify({
            'success': True,
            'errors': list(errors_by_line.values()),
            'total_words': len(words),
            'misspelled_words': len(misspelled),
            'accuracy_percentage': round(((len(words) - len(misspelled)) / len(words)) * 100, 1) if words else 100
        })
        
    except Exception as e:
        return jsonify({'error': f'Error checking spelling: {str(e)}'}), 500


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
    app.run(debug=True, host='0.0.0.0', port=8080)