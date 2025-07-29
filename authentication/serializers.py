from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    is_oauth_only_user = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'date_joined', 'avatar', 'is_email_verified', 'two_factor_enabled', 'is_oauth_only_user')
        read_only_fields = ('id', 'date_joined', 'is_email_verified', 'two_factor_enabled', 'is_oauth_only_user')
    
    def get_is_oauth_only_user(self, obj):
        return obj.is_oauth_only_user()


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