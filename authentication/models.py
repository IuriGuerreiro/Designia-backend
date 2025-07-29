from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
import random
import string
from datetime import timedelta
from django.utils import timezone


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)  # Changed to False - users must verify email first
    is_email_verified = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # 2FA fields
    two_factor_enabled = models.BooleanField(default=False)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def is_oauth_only_user(self):
        """Check if user is OAuth-only (no password set)"""
        return not self.has_usable_password()
    
    def __str__(self):
        return self.email


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='verification_tokens')
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)  # Token expires in 24 hours
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def __str__(self):
        return f"Verification token for {self.user.email}"


class EmailRequestAttempt(models.Model):
    """Track email request attempts for rate limiting"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='email_attempts')
    email = models.EmailField()
    request_type = models.CharField(max_length=30, choices=[
        ('email_verification', 'Email Verification'),
        ('password_reset', 'Password Reset'),
        ('two_factor_code', 'Two Factor Code'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['email', 'request_type', 'created_at']),
            models.Index(fields=['user', 'request_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"Email request: {self.email} - {self.request_type} at {self.created_at}"


class TwoFactorCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='two_factor_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    purpose = models.CharField(max_length=20, choices=[
        ('enable_2fa', 'Enable 2FA'),
        ('disable_2fa', 'Disable 2FA'),
        ('login', 'Login Verification'),
        ('set_password', 'Set Password'),
        ('reset_password', 'Reset Password'),
    ], default='enable_2fa')
    
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)  # 10 minutes expiry
        super().save(*args, **kwargs)
    
    def generate_code(self):
        return ''.join(random.choices(string.digits, k=6))
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()
    
    def __str__(self):
        return f"2FA code for {self.user.email} - {self.purpose}"