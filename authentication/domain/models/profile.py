from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from .user import CustomUser


class Profile(models.Model):
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("non_binary", "Non-binary"),
        ("prefer_not_to_say", "Prefer not to say"),
        ("other", "Other"),
    ]

    ACCOUNT_TYPE_CHOICES = [
        ("personal", "Personal"),
        ("business", "Business"),
        ("creator", "Creator"),
    ]

    PROFILE_VISIBILITY_CHOICES = [
        ("public", "Public"),
        ("private", "Private"),
        ("friends_only", "Friends Only"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    # Basic Profile Information
    bio = models.TextField(blank=True, null=True, max_length=500)
    location = models.CharField(max_length=100, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    pronouns = models.CharField(max_length=50, blank=True, null=True)

    # Contact Information
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    country_code = models.CharField(max_length=5, blank=True, null=True, default="+1")
    website = models.URLField(blank=True, null=True)

    # Professional Information
    job_title = models.CharField(max_length=100, blank=True, null=True)
    company = models.CharField(max_length=100, blank=True, null=True)

    # Address Information
    street_address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state_province = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)

    # Social Media Links
    instagram_url = models.URLField(blank=True, null=True)
    twitter_url = models.URLField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    facebook_url = models.URLField(blank=True, null=True)

    # Preferences
    timezone = models.CharField(max_length=50, blank=True, null=True, default="UTC")
    language_preference = models.CharField(max_length=10, blank=True, null=True, default="en")
    currency_preference = models.CharField(max_length=3, blank=True, null=True, default="USD")

    # Account Settings
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default="personal")
    profile_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default="public")

    # Verification & Status
    is_verified = models.BooleanField(default=False)
    is_verified_seller = models.BooleanField(default=False)
    seller_type = models.CharField(max_length=50, blank=True, null=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile_completion_percentage = models.IntegerField(default=0)

    # Profile Picture (S3 Storage)
    profile_picture_url = models.CharField(
        max_length=500, blank=True, null=True, help_text="S3 object key for profile picture"
    )

    # Marketing Preferences
    marketing_emails_enabled = models.BooleanField(default=True)
    newsletter_enabled = models.BooleanField(default=True)
    notifications_enabled = models.BooleanField(default=True)

    class Meta:
        app_label = "authentication"

    def calculate_profile_completion(self):
        """Calculate profile completion percentage"""

        fields_to_check = [
            "bio",
            "location",
            "birth_date",
            "phone_number",
            "job_title",
            "company",
            "city",
            "country",
            "profile_picture_url",
        ]

        completed_fields = []
        empty_fields = []

        for field in fields_to_check:
            field_value = getattr(self, field)
            if field_value:
                completed_fields.append(field)
            else:
                empty_fields.append(field)

        self.profile_completion_percentage = int((len(completed_fields) / len(fields_to_check)) * 100)

        return self.profile_completion_percentage

    def get_profile_picture_temp_url(self, expires_in: int = 3600) -> Optional[str]:
        """Get temporary URL for profile picture if it exists in S3"""
        if not self.profile_picture_url:
            return None

        try:
            from django.conf import settings

            if not getattr(settings, "USE_S3", False):
                return None

            from utils.s3_storage import get_s3_storage

            s3_storage = get_s3_storage()
            return s3_storage.get_file_url(self.profile_picture_url, expires_in=expires_in)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to generate temp URL for profile picture {self.profile_picture_url}: {str(e)}")
            return None

    def save(self, *args, **kwargs):
        self.calculate_profile_completion()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}'s Profile"


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, created, **kwargs):
    # Only save profile on user updates, not on creation
    # (creation is handled by create_user_profile signal)
    if not created:
        instance.profile.save()
