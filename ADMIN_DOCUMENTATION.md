# Admin Interface Documentation

## Overview
The admin interface provides comprehensive account management functionality for the Minecraft Education Toolkit. Admin users can create, manage, and delete user accounts along with all their associated data.

## Features

### 1. Account Creation
- Create new user accounts with comprehensive user information:
  - First name and surname for display purposes
  - Username for login (letters, numbers, hyphens, underscores only)
  - Email address for password reset functionality
  - Password with strength requirements (minimum 6 characters)
- Set admin privileges for new users
- Email uniqueness validation
- All fields are required for new accounts

### 2. Account Management
- View all user accounts with comprehensive information:
  - Full name (first name + surname) for easy identification
  - Username for login purposes
  - Email address for contact and password reset
  - Role status (Admin/User)
  - Account creation dates
  - User statistics (number of worlds, unpacked worlds)
- Enhanced display showing real names in navigation and welcome messages
- Identify current user and protected accounts

### 3. Account Deletion
- Delete user accounts with confirmation dialog
- Automatically removes all associated data:
  - Uploaded world files (.mcworld/.mctemplate)
  - Unpacked world folders and metadata
  - User metadata entries
- Protections in place:
  - Cannot delete admin account
  - Cannot delete your own account
  - Confirmation dialog shows what will be deleted

## Access Control
- Only users with admin privileges can access the admin panel
- Admin status is stored in the users.json file
- Navigation link only appears for admin users
- All admin routes check for admin privileges

## Data Management
- User data is stored in `users.json`
- Password hashing uses pbkdf2:sha256 method
- Automatic cleanup of orphaned data when users are deleted
- Maintains data integrity across all user operations

## Security Features
- Input validation for usernames and passwords
- CSRF protection through Flask forms
- Session-based authentication
- Protected account deletion (admin, current user)
- Secure password hashing

## Usage

### Accessing the Admin Panel
1. Log in with an admin account (default: admin/password123)
2. Click "Admin Panel" in the navigation menu
3. The admin dashboard will show all user accounts

### Creating New Users
1. In the admin panel, fill out the "Create New User Account" form:
   - **First Name**: Minimum 2 characters
   - **Surname**: Minimum 2 characters  
   - **Username**: 3+ characters, alphanumeric with hyphens/underscores
   - **Email**: Valid email address (used for password reset)
   - **Password**: 6+ characters
   - **Admin privileges**: Optional checkbox to grant admin access
2. All fields are required
3. Email addresses must be unique across all accounts
4. Click "Create User" to create the account

### Deleting Users
1. Find the user in the accounts table
2. Click the "Delete" button (not available for admin or current user)
3. Review the confirmation dialog showing what will be deleted
4. Click "Delete Account & Data" to confirm

## Default Admin Account
- **Name**: System Administrator
- **Username**: admin
- **Email**: admin@mcedu-toolkit.local
- **Password**: password123
- Cannot be deleted
- Always has admin privileges

## User Experience Enhancements
- Navigation bar shows user's full name instead of username
- Dashboard welcome message uses first name for personalization
- Admin panel displays full names for easier user identification
- Forgot password functionality (placeholder for future email integration)

## Data Migration
- Existing users are automatically migrated to include new fields
- Default values are assigned for missing first name, surname, and email
- Backward compatibility maintained with existing user accounts

## File Structure
- `users.json` - User account storage
- `templates/admin_panel.html` - Admin interface template
- Admin routes in `app.py` starting with `/admin`