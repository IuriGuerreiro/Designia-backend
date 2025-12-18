from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from authentication.domain.models import CustomUser, Profile

from .profile_serializers import ProfileSerializer


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()
    is_oauth_only_user = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "date_joined",
            "avatar",
            "is_email_verified",
            "two_factor_enabled",
            "is_oauth_only_user",
            "language",
            "role",
            "profile",
        )
        read_only_fields = (
            "id",
            "email",
            "date_joined",
            "is_email_verified",
            "two_factor_enabled",
            "is_oauth_only_user",
            "role",
        )

    def get_is_oauth_only_user(self, obj):
        return obj.is_oauth_only_user()

    def validate_username(self, value):
        """Ensure username is unique for this user"""
        if CustomUser.objects.filter(username=value).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def update(self, instance, validated_data):
        import logging

        logger = logging.getLogger(__name__)

        # Debug logging
        logger.info("=== PROFILE UPDATE DEBUG START ===")
        logger.info(f"User ID: {instance.id}, Username: {instance.username}")
        logger.info(f"Validated data received: {validated_data}")

        profile_data = validated_data.pop("profile", {})
        # Do not log raw profile payload
        try:
            profile_keys = list((profile_data or {}).keys())
        except Exception:
            profile_keys = []
        logger.info("Profile data keys received: %s", profile_keys)

        # Ensure profile exists
        if not hasattr(instance, "profile") or instance.profile is None:
            logger.warning(f"Profile doesn't exist for user {instance.id}, creating new profile")

            Profile.objects.create(user=instance)

        profile = instance.profile
        logger.info(f"Profile ID: {profile.id if profile else 'None'}")

        # Only update user fields that are provided in the request
        user_updated = False
        user_changes = []

        if "first_name" in validated_data:
            instance.first_name = validated_data["first_name"]
            user_changes.append("first_name")
            user_updated = True

        if "last_name" in validated_data:
            instance.last_name = validated_data["last_name"]
            user_changes.append("last_name")
            user_updated = True

        if "username" in validated_data:
            instance.username = validated_data["username"]
            user_changes.append("username")
            user_updated = True

        if user_updated:
            logger.info("User fields being updated: %s", user_changes)
            try:
                instance.save()
                logger.info("User instance saved successfully")
            except Exception as e:
                logger.error(f"Error saving user instance: {str(e)}")
                raise serializers.ValidationError(f"Error updating user: {str(e)}") from e
        else:
            logger.info("No user fields to update")

        # Only update profile fields that are explicitly provided
        profile_updated = False
        profile_changes = []

        try:
            for field_name, field_value in profile_data.items():
                # Only update if the field exists on the model
                if hasattr(profile, field_name):
                    _old_value = getattr(profile, field_name)
                    setattr(profile, field_name, field_value)
                    profile_changes.append(field_name)
                    profile_updated = True
                else:
                    logger.warning(f"Profile field '{field_name}' does not exist on model, skipping")

            if profile_updated:
                logger.info("Profile fields being updated: %s", profile_changes)
                old_completion = profile.profile_completion_percentage
                profile.save()  # This will trigger calculate_profile_completion()
                profile.refresh_from_db()  # Get updated completion percentage
                logger.info(
                    f"Profile saved successfully. Completion: {old_completion}% → {profile.profile_completion_percentage}%"
                )
            else:
                logger.info("No profile fields to update")

        except Exception as e:
            logger.error(f"Error updating profile: {str(e)}")
            # Avoid logging raw profile payload; include only field names
            logger.error("Profile fields present at error: %s", profile_keys)
            raise serializers.ValidationError(f"Error updating profile: {str(e)}") from e

        # End of profile update (no payload logged)
        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ("username", "email", "password", "password_confirm", "first_name", "last_name")

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError("Password fields didn't match.")
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        user = CustomUser.objects.create_user(**validated_data)
        return user


class GoogleAuthSerializer(serializers.Serializer):
    """
    Google Authentication Serializer
    """

    email = serializers.EmailField()
    sub = serializers.CharField()
    given_name = serializers.CharField(required=False, allow_blank=True)
    family_name = serializers.CharField(required=False, allow_blank=True)
    picture = serializers.URLField(required=False, allow_blank=True)
    email_verified = serializers.BooleanField(required=False)


class TwoFactorToggleSerializer(serializers.Serializer):
    """Serializer for toggling 2FA on/off"""

    enable = serializers.BooleanField()


class TwoFactorCodeRequestSerializer(serializers.Serializer):
    """Serializer for requesting a 2FA code"""

    purpose = serializers.ChoiceField(
        choices=[
            ("enable_2fa", "Enable 2FA"),
            ("disable_2fa", "Disable 2FA"),
        ]
    )


class TwoFactorConfirmSerializer(serializers.Serializer):
    """Serializer for confirming 2FA action (enable/disable)"""

    code = serializers.CharField(max_length=6, min_length=6)


class TwoFactorVerifySerializer(serializers.Serializer):
    """Serializer for verifying 2FA codes"""

    code = serializers.CharField(max_length=6, min_length=6)
    purpose = serializers.ChoiceField(
        choices=[
            ("enable_2fa", "Enable 2FA"),
            ("disable_2fa", "Disable 2FA"),
            ("login", "Login Verification"),
            ("set_password", "Set Password"),
            ("reset_password", "Reset Password"),
        ],
        default="enable_2fa",
    )


class SetPasswordRequestSerializer(serializers.Serializer):
    """Serializer for requesting password setup (OAuth users only)"""

    pass  # No fields needed, just triggers 2FA code generation


class SetPasswordVerifySerializer(serializers.Serializer):
    """Serializer for setting password with 2FA verification"""

    code = serializers.CharField(max_length=6, min_length=6)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError("Password fields didn't match.")
        return attrs


class LoginUserSerializer(serializers.ModelSerializer):
    """Lightweight serializer for login responses - only essential user data"""

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "avatar",
            "language",
            "role",
        )
        read_only_fields = fields
