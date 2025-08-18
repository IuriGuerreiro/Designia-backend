#!/usr/bin/env python
"""Fix user migration"""

import os
import sys
import django
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import connections
from django.contrib.auth import get_user_model

User = get_user_model()
sqlite_db = connections['sqlite']

print('Fixing user migration...')

# Get users from SQLite
with sqlite_db.cursor() as cursor:
    cursor.execute('SELECT * FROM authentication_customuser')
    users = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

print(f'Found {len(users)} users in SQLite')

# Clear existing users in MySQL
User.objects.all().delete()

# Insert users one by one to handle duplicates
for user_data in users:
    user_dict = dict(zip(columns, user_data))
    try:
        user = User.objects.create(
            id=user_dict['id'],
            username=user_dict['username'],
            email=user_dict['email'],
            first_name=user_dict.get('first_name', ''),
            last_name=user_dict.get('last_name', ''),
            is_active=user_dict.get('is_active', True),
            is_staff=user_dict.get('is_staff', False),
            is_superuser=user_dict.get('is_superuser', False),
            date_joined=user_dict.get('date_joined'),
            last_login=user_dict.get('last_login'),
            password=user_dict.get('password', ''),
            is_email_verified=user_dict.get('is_email_verified', False),
            two_factor_enabled=user_dict.get('two_factor_enabled', False),
            language=user_dict.get('language', 'en'),
            stripe_account_id=user_dict.get('stripe_account_id'),
        )
        print(f'✅ Created user: {user.username}')
    except Exception as e:
        print(f'❌ Failed to create user {user_dict.get("username")}: {e}')

print(f'Users in MySQL now: {User.objects.count()}')