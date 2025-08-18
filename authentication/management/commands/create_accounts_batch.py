"""
Django management command to create multiple user accounts from a JSON file or CSV file.

Usage:
    python manage.py create_accounts_batch --file accounts.json
    python manage.py create_accounts_batch --file accounts.csv --format csv

JSON Format:
[
    {
        "name": "John Doe",
        "username": "johndoe",
        "email": "john@example.com",
        "language": "en",
        "account_type": "personal"
    },
    {
        "name": "Jane Smith", 
        "username": "janesmith",
        "email": "jane@example.com",
        "language": "es",
        "account_type": "business"
    }
]

CSV Format:
name,username,email,language,account_type
John Doe,johndoe,john@example.com,en,personal
Jane Smith,janesmith,jane@example.com,es,business

Features:
- Supports JSON and CSV formats
- Creates CustomUser with email verified and active status
- Sets default password as 'D!ferente' for all accounts
- Handles duplicate usernames/emails gracefully
- Provides detailed success/error reporting
- Transaction support for rollback on critical errors
"""

import json
import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from authentication.models import CustomUser, Profile
import re


class Command(BaseCommand):
    help = 'Create multiple user accounts from JSON or CSV file (email verified, password: D!ferente)'

    def add_arguments(self, parser):
        # Required arguments
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to JSON or CSV file containing account data'
        )
        
        # Optional arguments
        parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'csv'],
            default='json',
            help='File format (default: json, auto-detected from extension)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip existing users instead of stopping on duplicates'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate data without creating accounts'
        )
        parser.add_argument(
            '--rollback-on-error',
            action='store_true',
            help='Rollback all changes if any account creation fails'
        )

    def validate_email(self, email):
        """Validate email format"""
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_regex, email) is not None

    def validate_language(self, language):
        """Validate language code against available choices"""
        valid_languages = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
        return language in valid_languages

    def split_name(self, full_name):
        """Split full name into first and last name"""
        name_parts = full_name.strip().split()
        if len(name_parts) == 1:
            return name_parts[0], ''
        elif len(name_parts) == 2:
            return name_parts[0], name_parts[1]
        else:
            return name_parts[0], ' '.join(name_parts[1:])

    def validate_account_data(self, account_data):
        """Validate individual account data"""
        errors = []
        
        # Required fields
        required_fields = ['name', 'username', 'email']
        for field in required_fields:
            if not account_data.get(field, '').strip():
                errors.append(f'Missing required field: {field}')
        
        if errors:
            return errors
        
        # Validate email
        email = account_data['email'].lower().strip()
        if not self.validate_email(email):
            errors.append(f'Invalid email format: {email}')
        
        # Validate username
        username = account_data['username'].strip()
        if len(username) < 3:
            errors.append('Username must be at least 3 characters long')
        
        # Validate name
        name = account_data['name'].strip()
        if len(name) < 2:
            errors.append('Name must be at least 2 characters long')
        
        # Validate optional fields
        language = account_data.get('language', 'en')
        if not self.validate_language(language):
            valid_langs = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
            errors.append(f'Invalid language code: {language}. Valid options: {", ".join(valid_langs)}')
        
        account_type = account_data.get('account_type', 'personal')
        if account_type not in ['personal', 'business', 'creator']:
            errors.append(f'Invalid account type: {account_type}. Valid options: personal, business, creator')
        
        return errors

    def load_accounts_from_json(self, file_path):
        """Load accounts from JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise CommandError('JSON file must contain an array of account objects')
            
            return data
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON format: {str(e)}')
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')

    def load_accounts_from_csv(self, file_path):
        """Load accounts from CSV file"""
        try:
            accounts = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):  # Start at 2 because header is row 1
                    # Clean up the data
                    account_data = {k.strip(): v.strip() for k, v in row.items() if k}
                    if account_data:  # Skip empty rows
                        accounts.append(account_data)
            
            return accounts
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV file: {str(e)}')

    def detect_file_format(self, file_path):
        """Auto-detect file format from extension"""
        _, ext = os.path.splitext(file_path.lower())
        if ext == '.json':
            return 'json'
        elif ext == '.csv':
            return 'csv'
        else:
            return 'json'  # Default

    def handle(self, *args, **options):
        file_path = options['file']
        file_format = options['format']
        force = options['force']
        dry_run = options['dry_run']
        rollback_on_error = options['rollback_on_error']

        # Auto-detect format if not specified explicitly
        if file_format == 'json' and not options.get('format_specified'):
            file_format = self.detect_file_format(file_path)

        # Load accounts data
        if file_format == 'json':
            accounts_data = self.load_accounts_from_json(file_path)
        else:
            accounts_data = self.load_accounts_from_csv(file_path)

        if not accounts_data:
            raise CommandError('No account data found in file')

        self.stdout.write(f'Found {len(accounts_data)} accounts to process...\n')

        # Validate all accounts first
        validation_errors = []
        for i, account_data in enumerate(accounts_data):
            errors = self.validate_account_data(account_data)
            if errors:
                validation_errors.append(f'Account {i + 1}: {"; ".join(errors)}')

        if validation_errors:
            self.stdout.write(self.style.ERROR('Validation errors found:'))
            for error in validation_errors:
                self.stdout.write(self.style.ERROR(f'  ❌ {error}'))
            raise CommandError('Fix validation errors before proceeding')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('✅ Dry run successful - all account data is valid'))
            return

        # Process accounts
        created_count = 0
        skipped_count = 0
        errors_count = 0
        
        def process_accounts():
            nonlocal created_count, skipped_count, errors_count
            
            for i, account_data in enumerate(accounts_data):
                try:
                    # Prepare data
                    username = account_data['username'].strip()
                    email = account_data['email'].lower().strip()
                    full_name = account_data['name'].strip()
                    language = account_data.get('language', 'en')
                    account_type = account_data.get('account_type', 'personal')
                    
                    first_name, last_name = self.split_name(full_name)

                    # Check for existing users
                    username_exists = CustomUser.objects.filter(username=username).exists()
                    email_exists = CustomUser.objects.filter(email=email).exists()

                    if username_exists or email_exists:
                        if force:
                            self.stdout.write(
                                self.style.WARNING(f'  ⏭️  Account {i + 1} ({username}): Skipped (user exists)')
                            )
                            skipped_count += 1
                            continue
                        else:
                            raise CommandError(f'Account {i + 1} ({username}): User already exists')

                    # Create user
                    user = CustomUser.objects.create_user(
                        username=username,
                        email=email,
                        password='D!ferente',
                        first_name=first_name,
                        last_name=last_name,
                        language=language,
                        is_email_verified=True,
                        is_active=True
                    )

                    # Update profile
                    profile = user.profile
                    profile.account_type = account_type
                    profile.save()

                    self.stdout.write(
                        self.style.SUCCESS(f'  ✅ Account {i + 1}: {username} ({email}) created successfully')
                    )
                    created_count += 1

                except Exception as e:
                    error_msg = f'Account {i + 1} ({account_data.get("username", "unknown")}): {str(e)}'
                    self.stdout.write(self.style.ERROR(f'  ❌ {error_msg}'))
                    errors_count += 1
                    
                    if not force:
                        raise CommandError(f'Account creation failed: {str(e)}')

        # Execute account creation
        if rollback_on_error:
            try:
                with transaction.atomic():
                    process_accounts()
            except Exception as e:
                raise CommandError(f'Transaction rolled back due to error: {str(e)}')
        else:
            process_accounts()

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'✅ Created: {created_count} accounts'))
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(f'⏭️  Skipped: {skipped_count} accounts'))
        if errors_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ Errors: {errors_count} accounts'))
        self.stdout.write(f'📄 Total processed: {len(accounts_data)} accounts')
        self.stdout.write('='*50)