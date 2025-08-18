#!/usr/bin/env python
"""
Standalone script to create user accounts in Django Designia backend.

This script can be run independently to create accounts with the Designia authentication system.
It sets up the Django environment and creates users with email verification confirmed.

Usage:
    python create_account_script.py --name "John Doe" --username "johndoe" --email "john@example.com"
    python create_account_script.py --name "Jane Smith" --username "janesmith" --email "jane@example.com" --language "es"

Features:
- Creates CustomUser with email verified and active status
- Sets default password as 'D!ferente'
- Creates associated Profile
- Handles duplicate usernames/emails gracefully
- Can be run outside Django management commands
"""

import os
import sys
import django
import argparse
import re
from pathlib import Path

# Add the Django project to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

# Now import Django models after setup
from django.db import transaction
from authentication.models import CustomUser, Profile


def validate_email(email):
    """Validate email format"""
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None


def validate_language(language):
    """Validate language code against available choices"""
    valid_languages = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
    return language in valid_languages


def split_name(full_name):
    """Split full name into first and last name"""
    name_parts = full_name.strip().split()
    if len(name_parts) == 1:
        return name_parts[0], ''
    elif len(name_parts) == 2:
        return name_parts[0], name_parts[1]
    else:
        # More than 2 parts, first word is first name, rest is last name
        return name_parts[0], ' '.join(name_parts[1:])


def create_account(name, username, email, language='en', account_type='personal', is_staff=False, is_superuser=False, force=False):
    """
    Create a user account with the specified parameters.
    
    Args:
        name (str): Full name of the user
        username (str): Username for the account
        email (str): Email address
        language (str): Language preference (default: 'en')
        account_type (str): Account type ('personal', 'business', 'creator')
        is_staff (bool): Make user a staff member
        is_superuser (bool): Make user a superuser
        force (bool): Skip existing users instead of raising error
    
    Returns:
        tuple: (success: bool, message: str, user: CustomUser or None)
    """
    
    # Validation
    email = email.lower().strip()
    
    if not validate_email(email):
        return False, f'Invalid email format: {email}', None

    if not validate_language(language):
        valid_langs = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
        return False, f'Invalid language code: {language}. Valid options: {", ".join(valid_langs)}', None

    if len(username) < 3:
        return False, 'Username must be at least 3 characters long', None

    if len(name.strip()) < 2:
        return False, 'Name must be at least 2 characters long', None

    if account_type not in ['personal', 'business', 'creator']:
        return False, f'Invalid account type: {account_type}. Valid options: personal, business, creator', None

    # Split full name
    first_name, last_name = split_name(name)

    # Check for existing users
    username_exists = CustomUser.objects.filter(username=username).exists()
    email_exists = CustomUser.objects.filter(email=email).exists()

    if username_exists:
        if force:
            return False, f'Username "{username}" already exists. Skipped due to force flag.', None
        else:
            return False, f'Username "{username}" already exists.', None

    if email_exists:
        if force:
            return False, f'Email "{email}" already exists. Skipped due to force flag.', None
        else:
            return False, f'Email "{email}" already exists.', None

    # Create user with transaction to ensure atomicity
    try:
        with transaction.atomic():
            # Create CustomUser
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password='D!ferente',  # Default password as specified
                first_name=first_name,
                last_name=last_name,
                language=language,
                is_email_verified=True,  # Email is confirmed by default
                is_active=True,  # Account is active
                is_staff=is_superuser or is_staff,  # Superuser implies staff
                is_superuser=is_superuser
            )

            # Update profile with account type
            # Profile is automatically created via post_save signal
            profile = user.profile
            profile.account_type = account_type
            profile.save()

            success_message = (
                f'✅ Successfully created user account:\n'
                f'   Username: {username}\n'
                f'   Email: {email}\n'
                f'   Name: {first_name} {last_name}\n'
                f'   Password: D!ferente\n'
                f'   Language: {language}\n'
                f'   Account Type: {account_type}\n'
                f'   Email Verified: Yes\n'
                f'   Active: Yes\n'
                f'   Staff: {"Yes" if user.is_staff else "No"}\n'
                f'   Superuser: {"Yes" if user.is_superuser else "No"}\n'
                f'   User ID: {user.id}'
            )
            
            return True, success_message, user

    except Exception as e:
        return False, f'Failed to create user account: {str(e)}', None


def main():
    """Main function to handle command line arguments and create account"""
    
    parser = argparse.ArgumentParser(
        description='Create user accounts for Django Designia backend'
    )
    
    # Required arguments
    parser.add_argument(
        '--name',
        type=str,
        required=True,
        help='Full name of the user (will be split into first and last name)'
    )
    parser.add_argument(
        '--username',
        type=str,
        required=True,
        help='Username for the account (must be unique)'
    )
    parser.add_argument(
        '--email',
        type=str,
        required=True,
        help='Email address for the account (must be unique and valid)'
    )
    
    # Optional arguments
    parser.add_argument(
        '--language',
        type=str,
        default='en',
        help='Language preference (default: en)'
    )
    parser.add_argument(
        '--account-type',
        type=str,
        choices=['personal', 'business', 'creator'],
        default='personal',
        help='Account type for profile (default: personal)'
    )
    parser.add_argument(
        '--is-staff',
        action='store_true',
        help='Make the user a staff member'
    )
    parser.add_argument(
        '--is-superuser',
        action='store_true',
        help='Make the user a superuser (implies staff)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force creation even if user exists (will skip existing users)'
    )
    
    args = parser.parse_args()
    
    # Create account
    success, message, user = create_account(
        name=args.name,
        username=args.username,
        email=args.email,
        language=args.language,
        account_type=args.account_type.replace('-', '_'),  # Convert account-type to account_type
        is_staff=args.is_staff,
        is_superuser=args.is_superuser,
        force=args.force
    )
    
    if success:
        print(message)
        return 0
    else:
        print(f"❌ Error: {message}")
        return 1


if __name__ == '__main__':
    exit(main())