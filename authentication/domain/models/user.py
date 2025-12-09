import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ("user", "User"),
        ("seller", "Seller"),
        ("admin", "Admin"),
    ]

    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("pt", "Portuguese"),
        ("es", "Spanish"),
        ("fr", "French"),
        ("de", "German"),
        ("it", "Italian"),
        ("ru", "Russian"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("zh", "Chinese"),
        ("ar", "Arabic"),
        ("hi", "Hindi"),
        ("nl", "Dutch"),
        ("sv", "Swedish"),
        ("da", "Danish"),
        ("no", "Norwegian"),
        ("fi", "Finnish"),
        ("pl", "Polish"),
        ("tr", "Turkish"),
        ("th", "Thai"),
        ("vi", "Vietnamese"),
        ("id", "Indonesian"),
        ("ms", "Malay"),
        ("he", "Hebrew"),
        ("cs", "Czech"),
        ("hu", "Hungarian"),
        ("ro", "Romanian"),
        ("bg", "Bulgarian"),
        ("hr", "Croatian"),
        ("sk", "Slovak"),
        ("sl", "Slovenian"),
        ("et", "Estonian"),
        ("lv", "Latvian"),
        ("lt", "Lithuanian"),
        ("mt", "Maltese"),
        ("ga", "Irish"),
        ("cy", "Welsh"),
        ("eu", "Basque"),
        ("ca", "Catalan"),
        ("gl", "Galician"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)  # Changed to False - users must verify email first
    is_email_verified = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    # Role system - simple field
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")

    # 2FA fields
    two_factor_enabled = models.BooleanField(default=False)

    # Language preference
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default="en")

    # Stripe Connect fields
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        app_label = "authentication"

    def is_oauth_only_user(self):
        """Check if user is OAuth-only (no password set)"""
        return not self.has_usable_password()

    def is_seller(self):
        """Check if user is a verified seller"""
        return self.role == "seller" or self.is_admin()

    def is_admin(self):
        """Check if user is an admin"""
        return self.role == "admin" or self.is_superuser

    def can_sell_products(self):
        """Check if user can create and sell products"""
        return self.is_seller() or self.is_admin()

    def __str__(self):
        return self.email
