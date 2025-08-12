#!/usr/bin/env python
"""
Quick script to verify email configuration
Run this to ensure Django is loading the correct SMTP settings
"""

import os
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.conf import settings

print("🔧 Current Django Email Configuration:")
print("="*50)
print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
print(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
print("="*50)

# Test expected values
expected_host = "smtp.ethereal.email"
expected_user = "presley34@ethereal.email"

if settings.EMAIL_HOST == expected_host and settings.EMAIL_HOST_USER == expected_user:
    print("✅ Configuration is CORRECT - Using Ethereal Email")
    print("📧 Emails will be sent to Ethereal test inbox")
    print("🌐 View emails at: https://ethereal.email/messages")
    print("🔑 Login: presley34@ethereal.email / 5MFyQRJSbGJ9urtDC9")
else:
    print("❌ Configuration is INCORRECT")
    print(f"Expected host: {expected_host}")
    print(f"Actual host: {settings.EMAIL_HOST}")
    print(f"Expected user: {expected_user}")
    print(f"Actual user: {settings.EMAIL_HOST_USER}")
    print("\n🔧 Fix: Restart your Django development server")
    print("   python manage.py runserver")