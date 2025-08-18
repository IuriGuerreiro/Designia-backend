# Account Creation Scripts Documentation

This document describes the various scripts available for creating user accounts in the Designia authentication system.

## Overview

The account creation system provides three different ways to create users:
1. **Django Management Command** - Single account creation
2. **Batch Management Command** - Multiple accounts from JSON/CSV
3. **Standalone Python Script** - Independent script for single accounts

All scripts create users with these default settings:
- **Password**: `D!ferente` (as specified)
- **Email Verified**: `True` (email confirmation bypassed)
- **Account Active**: `True` (ready to use immediately)
- **Profile Created**: Automatic profile creation with specified account type

## 🔧 Script 1: Single Account Creation (Django Management Command)

### Location
```
authentication/management/commands/create_account.py
```

### Usage
```bash
# Basic usage
python manage.py create_account --name "John Doe" --username "johndoe" --email "john@example.com"

# With optional parameters
python manage.py create_account \
    --name "Jane Smith" \
    --username "janesmith" \
    --email "jane@example.com" \
    --language "es" \
    --account-type "business" \
    --is-staff

# Force creation (skip existing users)
python manage.py create_account \
    --name "PayoutFailsWithAccount_closed@gmail.com" \
    --username "PayoutFailsWithAccount_closed@gmail.com" \
    --email "PayoutFailsWithAccount_closed@gmail.com" \
    --force
```

### Parameters

#### Required
- `--name`: Full name (will be split into first/last name)
- `--username`: Unique username (min 3 characters)
- `--email`: Valid email address (must be unique)

#### Optional
- `--language`: Language code (default: `en`)
  - Available: `en`, `es`, `fr`, `de`, `pt`, `it`, `ja`, `zh`, etc.
- `--account-type`: Profile account type (default: `personal`)
  - Options: `personal`, `business`, `creator`
- `--is-staff`: Make user a staff member
- `--is-superuser`: Make user a superuser (implies staff)
- `--force`: Skip existing users instead of failing

### Example Output
```
✅ Successfully created user account:
   Username: johndoe
   Email: john@example.com
   Name: John Doe
   Password: D!ferente
   Language: en
   Account Type: personal
   Email Verified: Yes
   Active: Yes
   Staff: No
   Superuser: No
   User ID: 42
```

## 📦 Script 2: Batch Account Creation (Django Management Command)

### Location
```
authentication/management/commands/create_accounts_batch.py
```

### Usage
```bash
# From JSON file
python manage.py create_accounts_batch --file example_accounts.json

# From CSV file  
python manage.py create_accounts_batch --file example_accounts.csv --format csv

# With options
python manage.py create_accounts_batch \
    --file accounts.json \
    --force \
    --dry-run \
    --rollback-on-error
```

### Parameters
- `--file`: Path to JSON or CSV file (required)
- `--format`: File format (`json` or `csv`, auto-detected from extension)
- `--force`: Skip existing users instead of stopping
- `--dry-run`: Validate data without creating accounts  
- `--rollback-on-error`: Rollback all changes if any account fails

### JSON File Format
```json
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
```

### CSV File Format
```csv
name,username,email,language,account_type
John Doe,johndoe,john@example.com,en,personal
Jane Smith,janesmith,jane@example.com,es,business
```

### Example Output
```
Found 5 accounts to process...

  ✅ Account 1: johndoe (john@example.com) created successfully
  ✅ Account 2: janesmith (jane@example.com) created successfully
  ⏭️  Account 3: admin (admin@example.com): Skipped (user exists)
  ✅ Account 4: carlosrod (carlos@example.com) created successfully
  ❌ Account 5: invalid (invalid-email): Invalid email format

==================================================
✅ Created: 3 accounts
⏭️  Skipped: 1 accounts  
❌ Errors: 1 accounts
📄 Total processed: 5 accounts
==================================================
```

## 🐍 Script 3: Standalone Python Script

### Location
```
create_account_script.py
```

### Usage
```bash
# Basic usage
python create_account_script.py --name "John Doe" --username "johndoe" --email "john@example.com"

# With options
python create_account_script.py \
    --name "Jane Smith" \
    --username "janesmith" \
    --email "jane@example.com" \
    --language "es" \
    --account-type "business" \
    --is-staff \
    --force
```

### Features
- Can be run independently of Django management commands
- Same parameters as the Django management command
- Sets up Django environment automatically
- Returns proper exit codes (0 = success, 1 = error)

### Example Output
```
✅ Successfully created user account:
   Username: johndoe
   Email: john@example.com
   Name: John Doe
   Password: D!ferente
   Language: en
   Account Type: personal
   Email Verified: Yes
   Active: Yes
   Staff: No
   Superuser: No
   User ID: 42
```

## 📝 Example Files Provided

### example_accounts.json
Contains 5 sample accounts with different languages and account types.

### example_accounts.csv  
Same data as JSON but in CSV format for testing.

## 🔍 Validation Features

All scripts include comprehensive validation:

### Email Validation
- Proper email format using regex
- Uniqueness check against existing users

### Username Validation  
- Minimum 3 characters
- Uniqueness check against existing users

### Name Validation
- Minimum 2 characters
- Automatic splitting into first/last name

### Language Validation
- Validates against Django's LANGUAGE_CHOICES
- Supports 25+ languages including English, Spanish, French, German, Portuguese, Italian, Japanese, Chinese, Arabic, Hindi, etc.

### Account Type Validation
- Must be one of: `personal`, `business`, `creator`

## 🛡️ Security Features

### Default Password
- All accounts use `D!ferente` as specified
- Users should change password on first login

### Email Verification
- All accounts created with `is_email_verified=True`
- Bypasses email confirmation process for admin-created accounts

### Account Activation
- All accounts created with `is_active=True`
- Ready to use immediately

### Staff/Superuser Options
- Optional staff and superuser privileges
- Superuser automatically includes staff privileges

## 🚨 Error Handling

### Duplicate Users
- Scripts detect existing usernames and emails
- `--force` flag allows skipping existing users
- Clear error messages for conflicts

### Data Validation Errors
- Comprehensive validation before account creation
- Batch scripts validate all records before processing
- Detailed error reporting with line numbers (CSV)

### Transaction Safety
- Single accounts use database transactions
- Batch processing supports `--rollback-on-error` for atomicity
- Prevents partial account creation on failures

## 📊 Testing the Scripts

### Test Single Account Creation
```bash
python manage.py create_account \
    --name "Test User" \
    --username "testuser" \
    --email "test@example.com"
```

### Test Batch Creation
```bash  
# Dry run first
python manage.py create_accounts_batch --file example_accounts.json --dry-run

# Real creation
python manage.py create_accounts_batch --file example_accounts.json
```

### Test Standalone Script
```bash
python create_account_script.py \
    --name "Script Test" \
    --username "scripttest" \
    --email "script@example.com"
```

## 🔧 Troubleshooting

### Common Issues

1. **"Username already exists"**
   - Use `--force` flag to skip existing users
   - Choose a different username

2. **"Invalid email format"**
   - Check email format (must include @ and domain)
   - Ensure no extra spaces

3. **"Invalid language code"**
   - Use valid language codes: en, es, fr, de, etc.
   - Check available languages in CustomUser.LANGUAGE_CHOICES

4. **"File not found"**
   - Check file path is correct
   - Use absolute paths if needed

5. **Django not set up (standalone script)**
   - Run from Designia-backend directory
   - Ensure Django settings module is correct

### Debugging Tips
- Use `--dry-run` with batch commands to test data
- Check Django logs for detailed error messages  
- Verify database connectivity
- Ensure all required Django apps are installed

## 📋 Summary

These scripts provide a comprehensive solution for creating user accounts in the Designia system:

- **Single accounts**: Use Django management command or standalone script
- **Multiple accounts**: Use batch command with JSON/CSV files  
- **All accounts**: Email verified, active, password "D!ferente"
- **Flexible**: Support for different languages, account types, and permissions
- **Safe**: Comprehensive validation and error handling
- **Production-ready**: Transaction safety and duplicate handling