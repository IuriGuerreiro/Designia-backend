#!/usr/bin/env python3
"""
Script to populate initial AppVersion data for the mandatory update system.
Run this script after migrating the database to set up initial version requirements.
"""

import os
import sys

import django

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Designia_backend.settings")
django.setup()

from system_info.models import AppVersion  # noqa: E402


def create_initial_versions():
    """Create initial app version records for Android and iOS."""

    # Android version
    android_version, created = AppVersion.objects.get_or_create(
        platform="android",
        defaults={
            "mandatory_version": "1.0.0",
            "latest_version": "1.0.0",
            "update_message": "Please update to the latest version to continue using Designia AR.",
            "download_url": "https://play.google.com/store/apps/details?id=com.designia.app",
            "is_active": True,
        },
    )

    if created:
        print(f"✅ Created Android version: {android_version}")
    else:
        print(f"ℹ️  Android version already exists: {android_version}")

    # iOS version
    ios_version, created = AppVersion.objects.get_or_create(
        platform="ios",
        defaults={
            "mandatory_version": "1.0.0",
            "latest_version": "1.0.0",
            "update_message": "Please update to the latest version to continue using Designia AR.",
            "download_url": "https://apps.apple.com/app/designia-ar/id123456789",
            "is_active": True,
        },
    )

    if created:
        print(f"✅ Created iOS version: {ios_version}")
    else:
        print(f"ℹ️  iOS version already exists: {ios_version}")

    print("\n📱 App version setup complete!")
    print("\nTo test mandatory updates:")
    print("1. Update the mandatory_version field to a higher version (e.g., '1.1.0')")
    print("2. Keep your app version lower (e.g., '1.0.0' in package.json)")
    print("3. The app will show the mandatory update modal on next launch")


def update_to_example_mandatory_update():
    """Example: Set up a mandatory update scenario for testing."""

    # Update Android to require version 1.1.0
    android_version = AppVersion.objects.filter(platform="android").first()
    if android_version:
        android_version.mandatory_version = "1.1.0"
        android_version.latest_version = "1.2.0"
        android_version.update_message = (
            "A critical security update is required. Please update to continue using Designia AR."
        )
        android_version.save()
        print(f"🔄 Updated Android version for mandatory update: {android_version}")

    # Update iOS to require version 1.1.0
    ios_version = AppVersion.objects.filter(platform="ios").first()
    if ios_version:
        ios_version.mandatory_version = "1.1.0"
        ios_version.latest_version = "1.2.0"
        ios_version.update_message = (
            "A critical security update is required. Please update to continue using Designia AR."
        )
        ios_version.save()
        print(f"🔄 Updated iOS version for mandatory update: {ios_version}")

    print("\n🚨 Mandatory update scenario configured!")
    print("Your app (version 1.0.0) will now require updating to 1.1.0+")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-mandatory":
        update_to_example_mandatory_update()
    else:
        create_initial_versions()
