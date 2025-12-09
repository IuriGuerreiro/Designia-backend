from rest_framework import serializers

from authentication.domain.models import CustomUser, Profile


class ProfileSerializer(serializers.ModelSerializer):
    profile_completion_percentage = serializers.ReadOnlyField()
    profile_picture_temp_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            # Basic Profile Information
            "bio",
            "location",
            "birth_date",
            "gender",
            "pronouns",
            # Contact Information
            "phone_number",
            "country_code",
            "website",
            # Professional Information
            "job_title",
            "company",
            # Address Information
            "street_address",
            "city",
            "state_province",
            "country",
            "postal_code",
            # Social Media Links
            "instagram_url",
            "twitter_url",
            "linkedin_url",
            "facebook_url",
            # Preferences
            "timezone",
            "language_preference",
            "currency_preference",
            # Account Settings
            "account_type",
            "profile_visibility",
            # Verification & Status (read-only)
            "is_verified",
            "is_verified_seller",
            "seller_type",
            # Metadata (read-only)
            "created_at",
            "updated_at",
            "profile_completion_percentage",
            # Profile Picture
            "profile_picture_url",
            "profile_picture_temp_url",
            # Marketing Preferences
            "marketing_emails_enabled",
            "newsletter_enabled",
            "notifications_enabled",
        )
        read_only_fields = (
            "is_verified",
            "is_verified_seller",
            "seller_type",
            "created_at",
            "updated_at",
            "profile_completion_percentage",
            "profile_picture_temp_url",
        )

    def validate_website(self, value):
        """Custom validation for website URL"""
        if not value or value.strip() == "":
            return value
        return self._validate_url(value, "website")

    def validate_instagram_url(self, value):
        """Custom validation for Instagram URL"""
        if not value or value.strip() == "":
            return value
        return self._validate_url(value, "instagram")

    def validate_twitter_url(self, value):
        """Custom validation for Twitter URL"""
        if not value or value.strip() == "":
            return value
        return self._validate_url(value, "twitter")

    def validate_linkedin_url(self, value):
        """Custom validation for LinkedIn URL"""
        if not value or value.strip() == "":
            return value
        return self._validate_url(value, "linkedin")

    def validate_facebook_url(self, value):
        """Custom validation for Facebook URL"""
        if not value or value.strip() == "":
            return value
        return self._validate_url(value, "facebook")

    def _validate_url(self, value, field_type):
        """Helper method to validate and format URLs"""
        import logging

        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.core.validators import URLValidator

        logger = logging.getLogger(__name__)
        logger.info(f"Validating {field_type} URL: '{value}'")

        trimmed_value = value.strip()

        # If it's empty, return as is
        if not trimmed_value:
            return trimmed_value

        # Auto-format URL if it doesn't have a protocol
        formatted_url = trimmed_value
        if not formatted_url.startswith(("http://", "https://")):
            if formatted_url.startswith("www."):
                formatted_url = f"https://{formatted_url}"
            elif "." in formatted_url:
                formatted_url = f"https://{formatted_url}"

        logger.info(f"Formatted {field_type} URL: '{trimmed_value}' → '{formatted_url}'")

        # Validate the formatted URL
        validator = URLValidator()
        try:
            validator(formatted_url)
            logger.info(f"URL validation passed for {field_type}")
            return formatted_url
        except DjangoValidationError as e:
            logger.error(f"URL validation failed for {field_type}: {e}")
            raise serializers.ValidationError("Please enter a valid URL. Example: https://example.com") from e

    def get_profile_picture_temp_url(self, obj):
        """Get temporary URL for profile picture"""
        return obj.get_profile_picture_temp_url()


class PublicProfileSerializer(serializers.ModelSerializer):
    profile_picture_temp_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ("bio", "location", "website", "profile_picture_temp_url")

    def get_profile_picture_temp_url(self, obj):
        """Get temporary URL for profile picture"""
        return obj.get_profile_picture_temp_url()


class PublicUserSerializer(serializers.ModelSerializer):
    profile = PublicProfileSerializer(read_only=True)
    # Expose select profile fields at top-level for convenience in UI
    bio = serializers.CharField(source="profile.bio", read_only=True)
    location = serializers.CharField(source="profile.location", read_only=True)
    website = serializers.CharField(source="profile.website", read_only=True)
    job_title = serializers.CharField(source="profile.job_title", read_only=True)
    company = serializers.CharField(source="profile.company", read_only=True)
    instagram_url = serializers.CharField(source="profile.instagram_url", read_only=True)
    twitter_url = serializers.CharField(source="profile.twitter_url", read_only=True)
    linkedin_url = serializers.CharField(source="profile.linkedin_url", read_only=True)
    facebook_url = serializers.CharField(source="profile.facebook_url", read_only=True)
    is_verified_seller = serializers.BooleanField(source="profile.is_verified_seller", read_only=True)
    seller_type = serializers.CharField(source="profile.seller_type", read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "avatar",
            "date_joined",
            "profile",
            # Flattened profile fields commonly used in the seller page
            "bio",
            "location",
            "website",
            "job_title",
            "company",
            "instagram_url",
            "twitter_url",
            "linkedin_url",
            "facebook_url",
            "is_verified_seller",
            "seller_type",
        )
