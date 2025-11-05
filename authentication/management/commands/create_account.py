"""
Django management command to create user accounts with predefined settings.

Usage:
    python manage.py create_account --name "Full Name" --username "user123" --email "user@example.com"
    python manage.py create_account --name "John Doe" --username "johndoe" --email "john@example.com" --language "en" --account-type "personal"

Features:
- Creates CustomUser with email verified and active status
- Sets default password as 'D!ferente'
- Creates associated Profile
- Handles duplicate usernames/emails gracefully
- Supports optional parameters like language and account type
"""

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from authentication.models import CustomUser


class Command(BaseCommand):
    help = "Create a user account with predefined settings (email verified, password: D!ferente)"

    def add_arguments(self, parser):
        # Required arguments
        parser.add_argument(
            "--name", type=str, required=True, help="Full name of the user (will be split into first and last name)"
        )
        parser.add_argument("--username", type=str, required=True, help="Username for the account (must be unique)")
        parser.add_argument(
            "--email", type=str, required=True, help="Email address for the account (must be unique and valid)"
        )

        # Optional arguments
        parser.add_argument("--language", type=str, default="en", help="Language preference (default: en)")
        parser.add_argument(
            "--account-type",
            type=str,
            choices=["personal", "business", "creator"],
            default="personal",
            help="Account type for profile (default: personal)",
        )
        parser.add_argument("--is-staff", action="store_true", help="Make the user a staff member")
        parser.add_argument("--is-superuser", action="store_true", help="Make the user a superuser (implies staff)")
        parser.add_argument(
            "--force", action="store_true", help="Force creation even if user exists (will skip existing users)"
        )

    def validate_email(self, email):
        """Validate email format"""
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(email_regex, email) is not None

    def validate_language(self, language):
        """Validate language code against available choices"""
        valid_languages = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
        return language in valid_languages

    def split_name(self, full_name):
        """Split full name into first and last name"""
        name_parts = full_name.strip().split()
        if len(name_parts) == 1:
            return name_parts[0], ""
        elif len(name_parts) == 2:
            return name_parts[0], name_parts[1]
        else:
            # More than 2 parts, first word is first name, rest is last name
            return name_parts[0], " ".join(name_parts[1:])

    def handle(self, *args, **options):
        # Extract and validate arguments
        full_name = options["name"]
        username = options["username"]
        email = options["email"].lower()
        language = options["language"]
        account_type = options["account_type"]
        is_staff = options["is_staff"]
        is_superuser = options["is_superuser"]
        force = options["force"]

        # Validation
        if not self.validate_email(email):
            raise CommandError(f"Invalid email format: {email}")

        if not self.validate_language(language):
            valid_langs = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
            raise CommandError(f'Invalid language code: {language}. Valid options: {", ".join(valid_langs)}')

        if len(username) < 3:
            raise CommandError("Username must be at least 3 characters long")

        if len(full_name.strip()) < 2:
            raise CommandError("Name must be at least 2 characters long")

        # Split full name
        first_name, last_name = self.split_name(full_name)

        # Check for existing users
        username_exists = CustomUser.objects.filter(username=username).exists()
        email_exists = CustomUser.objects.filter(email=email).exists()

        if username_exists:
            if force:
                self.stdout.write(
                    self.style.WARNING(f'Username "{username}" already exists. Skipping due to --force flag.')
                )
                return
            else:
                raise CommandError(f'Username "{username}" already exists. Use --force to skip existing users.')

        if email_exists:
            if force:
                self.stdout.write(self.style.WARNING(f'Email "{email}" already exists. Skipping due to --force flag.'))
                return
            else:
                raise CommandError(f'Email "{email}" already exists. Use --force to skip existing users.')

        # Create user with transaction to ensure atomicity
        try:
            with transaction.atomic():
                # Create CustomUser
                user = CustomUser.objects.create_user(
                    username=username,
                    email=email,
                    password="D!ferente",  # Default password as specified
                    first_name=first_name,
                    last_name=last_name,
                    language=language,
                    is_email_verified=True,  # Email is confirmed by default
                    is_active=True,  # Account is active
                    is_staff=is_superuser or is_staff,  # Superuser implies staff
                    is_superuser=is_superuser,
                )

                # Update profile with account type
                # Profile is automatically created via post_save signal
                profile = user.profile
                profile.account_type = account_type
                profile.save()

                # Success message
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Successfully created user account:\n"
                        f"   Username: {username}\n"
                        f"   Email: {email}\n"
                        f"   Name: {first_name} {last_name}\n"
                        f"   Password: D!ferente\n"
                        f"   Language: {language}\n"
                        f"   Account Type: {account_type}\n"
                        f"   Email Verified: Yes\n"
                        f"   Active: Yes\n"
                        f'   Staff: {"Yes" if user.is_staff else "No"}\n'
                        f'   Superuser: {"Yes" if user.is_superuser else "No"}\n'
                        f"   User ID: {user.id}"
                    )
                )

        except Exception as e:
            raise CommandError(f"Failed to create user account: {str(e)}") from e
