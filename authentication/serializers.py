from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser, Profile


class ProfileSerializer(serializers.ModelSerializer):
    profile_completion_percentage = serializers.ReadOnlyField()
    profile_picture_temp_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = (
            # Basic Profile Information
            'bio', 'location', 'birth_date', 'gender', 'pronouns',
            
            # Contact Information
            'phone_number', 'country_code', 'website',
            
            # Professional Information
            'job_title', 'company',
            
            # Address Information
            'street_address', 'city', 'state_province', 'country', 'postal_code',
            
            # Social Media Links
            'instagram_url', 'twitter_url', 'linkedin_url', 'facebook_url',
            
            # Preferences
            'timezone', 'language_preference', 'currency_preference',
            
            # Account Settings
            'account_type', 'profile_visibility',
            
            # Verification & Status (read-only)
            'is_verified', 'is_verified_seller', 'seller_type',
            
            # Metadata (read-only)
            'created_at', 'updated_at', 'profile_completion_percentage',
            
            # Profile Picture
            'profile_picture_url', 'profile_picture_temp_url',
            
            # Marketing Preferences
            'marketing_emails_enabled', 'newsletter_enabled', 'notifications_enabled'
        )
        read_only_fields = (
            'is_verified', 'is_verified_seller', 'seller_type',
            'created_at', 'updated_at', 'profile_completion_percentage', 'profile_picture_temp_url'
        )

    def validate_website(self, value):
        """Custom validation for website URL"""
        if not value or value.strip() == '':
            return value
        return self._validate_url(value, 'website')
    
    def validate_instagram_url(self, value):
        """Custom validation for Instagram URL"""
        if not value or value.strip() == '':
            return value
        return self._validate_url(value, 'instagram')
    
    def validate_twitter_url(self, value):
        """Custom validation for Twitter URL"""
        if not value or value.strip() == '':
            return value
        return self._validate_url(value, 'twitter')
        
    def validate_linkedin_url(self, value):
        """Custom validation for LinkedIn URL"""
        if not value or value.strip() == '':
            return value
        return self._validate_url(value, 'linkedin')
    
    def validate_facebook_url(self, value):
        """Custom validation for Facebook URL"""
        if not value or value.strip() == '':
            return value
        return self._validate_url(value, 'facebook')
    
    def _validate_url(self, value, field_type):
        """Helper method to validate and format URLs"""
        import logging
        from django.core.validators import URLValidator
        from django.core.exceptions import ValidationError as DjangoValidationError
        
        logger = logging.getLogger(__name__)
        logger.info(f"Validating {field_type} URL: '{value}'")
        
        trimmed_value = value.strip()
        
        # If it's empty, return as is
        if not trimmed_value:
            return trimmed_value
            
        # Auto-format URL if it doesn't have a protocol
        formatted_url = trimmed_value
        if not formatted_url.startswith(('http://', 'https://')):
            if formatted_url.startswith('www.'):
                formatted_url = f'https://{formatted_url}'
            elif '.' in formatted_url:
                formatted_url = f'https://{formatted_url}'
        
        logger.info(f"Formatted {field_type} URL: '{trimmed_value}' → '{formatted_url}'")
        
        # Validate the formatted URL
        validator = URLValidator()
        try:
            validator(formatted_url)
            logger.info(f"URL validation passed for {field_type}")
            return formatted_url
        except DjangoValidationError as e:
            logger.error(f"URL validation failed for {field_type}: {e}")
            raise serializers.ValidationError(f"Please enter a valid URL. Example: https://example.com")

    def get_profile_picture_temp_url(self, obj):
        """Get temporary URL for profile picture"""
        return obj.get_profile_picture_temp_url()


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()
    is_oauth_only_user = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'date_joined', 'avatar', 'is_email_verified', 'two_factor_enabled', 'is_oauth_only_user', 'language', 'role', 'profile')
        read_only_fields = ('id', 'email', 'date_joined', 'is_email_verified', 'two_factor_enabled', 'is_oauth_only_user', 'role')

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
        logger.info(f"=== PROFILE UPDATE DEBUG START ===")
        logger.info(f"User ID: {instance.id}, Username: {instance.username}")
        logger.info(f"Validated data received: {validated_data}")
        
        profile_data = validated_data.pop('profile', {})
        logger.info(f"Profile data extracted: {profile_data}")
        
        # Ensure profile exists
        if not hasattr(instance, 'profile') or instance.profile is None:
            logger.warning(f"Profile doesn't exist for user {instance.id}, creating new profile")
            from .models import Profile
            Profile.objects.create(user=instance)
        
        profile = instance.profile
        logger.info(f"Profile ID: {profile.id if profile else 'None'}")

        # Only update user fields that are provided in the request
        user_updated = False
        user_changes = []
        
        if 'first_name' in validated_data:
            old_value = instance.first_name
            new_value = validated_data['first_name']
            instance.first_name = new_value
            user_changes.append(f"first_name: '{old_value}' → '{new_value}'")
            user_updated = True
            
        if 'last_name' in validated_data:
            old_value = instance.last_name
            new_value = validated_data['last_name']
            instance.last_name = new_value
            user_changes.append(f"last_name: '{old_value}' → '{new_value}'")
            user_updated = True
            
        if 'username' in validated_data:
            old_value = instance.username
            new_value = validated_data['username']
            instance.username = new_value
            user_changes.append(f"username: '{old_value}' → '{new_value}'")
            user_updated = True
        
        if user_updated:
            logger.info(f"User fields being updated: {user_changes}")
            try:
                instance.save()
                logger.info("User instance saved successfully")
            except Exception as e:
                logger.error(f"Error saving user instance: {str(e)}")
                raise serializers.ValidationError(f"Error updating user: {str(e)}")
        else:
            logger.info("No user fields to update")

        # Only update profile fields that are explicitly provided
        profile_updated = False
        profile_changes = []
        
        try:
            for field_name, field_value in profile_data.items():
                # Only update if the field exists on the model
                if hasattr(profile, field_name):
                    old_value = getattr(profile, field_name)
                    setattr(profile, field_name, field_value)
                    profile_changes.append(f"{field_name}: '{old_value}' → '{field_value}'")
                    profile_updated = True
                else:
                    logger.warning(f"Profile field '{field_name}' does not exist on model, skipping")
            
            if profile_updated:
                logger.info(f"Profile fields being updated: {profile_changes}")
                old_completion = profile.profile_completion_percentage
                profile.save()  # This will trigger calculate_profile_completion()
                profile.refresh_from_db()  # Get updated completion percentage
                logger.info(f"Profile saved successfully. Completion: {old_completion}% → {profile.profile_completion_percentage}%")
            else:
                logger.info("No profile fields to update")
                
        except Exception as e:
            logger.error(f"Error updating profile: {str(e)}")
            logger.error(f"Profile data that caused error: {profile_data}")
            raise serializers.ValidationError(f"Error updating profile: {str(e)}")

        logger.info(f"=== PROFILE UPDATE DEBUG END ===")
        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password', 'password_confirm', 'first_name', 'last_name')

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Password fields didn't match.")
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = CustomUser.objects.create_user(**validated_data)
        return user


class GoogleAuthSerializer(serializers.Serializer):
    """
    Google Authentication Serializer - exact copy from YummiAI
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


class TwoFactorVerifySerializer(serializers.Serializer):
    """Serializer for verifying 2FA codes"""
    code = serializers.CharField(max_length=6, min_length=6)
    purpose = serializers.ChoiceField(choices=[
        ('enable_2fa', 'Enable 2FA'),
        ('disable_2fa', 'Disable 2FA'),
        ('login', 'Login Verification'),
        ('set_password', 'Set Password'),
        ('reset_password', 'Reset Password'),
    ], default='enable_2fa')


class SetPasswordRequestSerializer(serializers.Serializer):
    """Serializer for requesting password setup (OAuth users only)"""
    pass  # No fields needed, just triggers 2FA code generation


class SetPasswordVerifySerializer(serializers.Serializer):
    """Serializer for setting password with 2FA verification"""
    code = serializers.CharField(max_length=6, min_length=6)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Password fields didn't match.")
        return attrs


class PublicProfileSerializer(serializers.ModelSerializer):
    profile_picture_temp_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = ('bio', 'location', 'website', 'profile_picture_temp_url')
    
    def get_profile_picture_temp_url(self, obj):
        """Get temporary URL for profile picture"""
        return obj.get_profile_picture_temp_url()


class PublicUserSerializer(serializers.ModelSerializer):
    profile = PublicProfileSerializer(read_only=True)
    # Expose select profile fields at top-level for convenience in UI
    bio = serializers.CharField(source='profile.bio', read_only=True)
    location = serializers.CharField(source='profile.location', read_only=True)
    website = serializers.CharField(source='profile.website', read_only=True)
    job_title = serializers.CharField(source='profile.job_title', read_only=True)
    company = serializers.CharField(source='profile.company', read_only=True)
    instagram_url = serializers.CharField(source='profile.instagram_url', read_only=True)
    twitter_url = serializers.CharField(source='profile.twitter_url', read_only=True)
    linkedin_url = serializers.CharField(source='profile.linkedin_url', read_only=True)
    facebook_url = serializers.CharField(source='profile.facebook_url', read_only=True)
    is_verified_seller = serializers.BooleanField(source='profile.is_verified_seller', read_only=True)
    seller_type = serializers.CharField(source='profile.seller_type', read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'id', 'username', 'first_name', 'last_name', 'avatar', 'date_joined',
            'profile',
            # Flattened profile fields commonly used in the seller page
            'bio', 'location', 'website', 'job_title', 'company',
            'instagram_url', 'twitter_url', 'linkedin_url', 'facebook_url',
            'is_verified_seller', 'seller_type',
        )
