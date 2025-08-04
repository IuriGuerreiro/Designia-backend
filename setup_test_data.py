#!/usr/bin/env python3
"""
Quick setup script to populate test data for the marketplace
Run this after setting up the Django project
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.core.management import call_command

def main():
    print("Setting up marketplace test data...")
    
    print("1. Running migrations...")
    call_command('migrate')
    
    print("2. Creating test data...")
    call_command('create_test_data', '--clear')
    
    print("\n✅ Setup complete!")
    print("📝 You now have:")
    print("   - Categories for different furniture types")
    print("   - Sample products with realistic data")
    print("   - Test users that can act as sellers")
    print("\n🚀 Start your Django server and test the marketplace:")
    print("   python manage.py runserver 192.168.3.2:8001")

if __name__ == '__main__':
    main()