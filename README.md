# Minecraft Education Toolkit (MCEdu Toolkit)

A comprehensive Python Flask web application for managing and analyzing Minecraft Education content. This toolkit provides educators with powerful tools to upload, unpack, analyze, and repack Minecraft Education worlds and templates.

## 🚀 Features

### 📁 File Management
- **Upload & Store**: Upload .mcworld and .mctemplate files with secure storage
- **Download & Delete**: Manage your uploaded files with full CRUD operations
- **Version Control**: Automatic versioning system for repacked worlds
- **File Validation**: Secure file type validation and size management

### 📦 World Unpacking & Repacking
- **Smart Unpacking**: Extract world files with automatic folder organization
- **Repack Worlds**: Convert modified unpacked worlds back to .mcworld/.mctemplate
- **Version Numbering**: Automatic version increments (e.g., `world_v1.mcworld`, `world_v2.mcworld`)
- **Metadata Tracking**: Complete traceability of unpacked and repacked worlds

### 🔍 Language Analysis Tools
- **Language File Discovery**: Automatically find and catalog all .lang files in worlds
- **Readability Analysis**: Comprehensive text analysis using multiple metrics:
  - Flesch Reading Ease Score
  - Flesch-Kincaid Grade Level
  - Gunning Fog Index
  - SMOG Index
  - Coleman-Liau Index
  - Automated Readability Index
- **Educational Insights**: Target age recommendations and reading level classifications
- **Sample Text Preview**: View extracted text content from language files

### 📄 PDF Reports
- **Comprehensive Reports**: Generate professional PDF analysis reports
- **Detailed Metrics**: Include all readability scores and educational recommendations
- **World Metadata**: Complete world information and analysis context
- **Downloadable**: Timestamped PDF files for record keeping and sharing

### 🔐 User Management
- **Secure Authentication**: Flask-Login based user system
- **Multi-user Support**: Admin and standard user roles
- **Session Management**: Secure login/logout functionality

### 🎨 User Interface
- **Responsive Design**: Mobile-friendly Bootstrap interface
- **Intuitive Navigation**: Clear, organized dashboard and tool pages
- **Status Indicators**: Visual feedback for world states (Packed/Unpacked/Repacked)
- **Real-time Feedback**: Flash messages for operation status

## 📋 Installation

### Prerequisites
- Python 3.8 or higher
- Git (for cloning the repository)

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd mcedu__toolkit
   ```

2. **Create and activate virtual environment:**
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download NLTK data (required for language analysis):**
   ```bash
   python -c "import nltk; nltk.download('punkt')"
   ```

## 🎯 Quick Start

1. **Start the application:**
   ```bash
   # Ensure virtual environment is activated
   python app.py
   ```

2. **Access the application:**
   Open your web browser and navigate to: `http://localhost:5000`

3. **Login with demo credentials:**
   - **Admin**: `admin` / `password123`
   - **User**: `user` / `user123`

## 📖 Usage Guide

### Uploading Worlds
1. Navigate to "Add New World" from the dashboard
2. Select your .mcworld or .mctemplate file
3. Upload and view in "Your Worlds" list

### Unpacking Worlds
1. In "Your Worlds", click "Unpack" on any packed world
2. World will be extracted and appear in "Unpacked Worlds" list
3. Original world remains available for download

### Language Analysis
1. From an unpacked world, click "Language Tools"
2. Use "Find Language Files" to discover available .lang files
3. Run "Language Analysis" for comprehensive readability metrics
4. Download PDF report for detailed analysis

### Repacking Worlds
1. In "Unpacked Worlds", click "Repack" on any unpacked world
2. System creates a new versioned world file
3. Repacked world appears in "Your Worlds" with version number

## 🏗️ Project Structure

```
mcedu__toolkit/
├── app.py                     # Main Flask application
├── requirements.txt           # Python dependencies
├── README.md                 # Documentation
├── store/                    # Uploaded world files
├── unpacked/                 # Extracted world contents
├── metadata.json             # World metadata
├── unpacked_metadata.json    # Unpacked world metadata
└── templates/                # HTML templates
    ├── base.html             # Base template with navigation
    ├── login.html            # Login page
    ├── dashboard.html        # Main dashboard
    ├── add_world.html        # Upload page
    ├── language_tools.html   # Language tools main page
    └── language_tools_world.html # Individual world analysis
```

## 🔧 Technical Details

### Dependencies
- **Flask 3.0.0**: Web framework
- **Flask-Login 0.6.3**: User session management
- **textstat 0.7.1**: Text readability analysis
- **nltk 3.8.1**: Natural language processing
- **reportlab 4.0.7**: PDF generation
- **Werkzeug 3.0.1**: WSGI utilities

### Supported File Types
- `.mcworld` - Minecraft Education world files
- `.mctemplate` - Minecraft Education template files

### Analysis Metrics
The language analysis provides multiple readability metrics:

- **Flesch Reading Ease**: 0-100 scale (higher = easier)
- **Grade Level Scores**: Educational grade equivalents
- **Target Age**: Precise age recommendations (not ranges)
- **Reading Time**: Estimated reading duration
- **Text Statistics**: Word count, sentence count, syllable analysis

## 🔒 Security Features

- Secure file upload with type validation
- Path traversal protection
- Session-based authentication
- File size limits (500MB max)
- Input sanitization and validation

## 🛠️ Configuration

### Environment Variables
You can configure the application using these settings in `app.py`:

- `SECRET_KEY`: Change for production deployment
- `UPLOAD_FOLDER`: Directory for uploaded files
- `UNPACKED_FOLDER`: Directory for extracted worlds
- `MAX_CONTENT_LENGTH`: Maximum file upload size

### Production Deployment

**Before deploying to production:**

1. Change the `SECRET_KEY` in `app.py`
2. Implement proper database for user management
3. Set up HTTPS/SSL
4. Configure proper logging
5. Set `debug=False` in the Flask app
6. Use a production WSGI server (e.g., Gunicorn)

## 🔄 Backup & Data Management

The application stores data in:
- `store/`: Uploaded world files
- `unpacked/`: Extracted world contents
- `metadata.json`: World metadata
- `unpacked_metadata.json`: Unpacked world tracking

**Backup these files regularly** to preserve your data.

## 🆘 Troubleshooting

### Common Issues

1. **NLTK Data Missing**: Run `python -c "import nltk; nltk.download('punkt')"`
2. **File Upload Fails**: Check file size (500MB limit) and file type (.mcworld/.mctemplate only)
3. **Language Analysis Errors**: Ensure world contains .lang files with sufficient text content
4. **PDF Generation Fails**: Verify reportlab installation: `pip install reportlab`

### Error Recovery

The application includes automatic error recovery:
- Inconsistent unpacked status detection and repair
- Orphaned metadata cleanup
- File system validation

## 🤝 Contributing

We welcome contributions! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is open source. Please add appropriate license information.

## 📞 Support

For support, feature requests, or bug reports, please create an issue in the repository.

---

**MCEdu Toolkit** - Empowering educators with advanced Minecraft Education content management and analysis tools.

This project is open source and available under the MIT License.