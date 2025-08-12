from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
import random
import string
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


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


class Profile(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('non_binary', 'Non-binary'),
        ('prefer_not_to_say', 'Prefer not to say'),
        ('other', 'Other'),
    ]
    
    ACCOUNT_TYPE_CHOICES = [
        ('personal', 'Personal'),
        ('business', 'Business'),
        ('creator', 'Creator'),
    ]
    
    PROFILE_VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('private', 'Private'),
        ('friends_only', 'Friends Only'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    
    # Basic Profile Information
    bio = models.TextField(blank=True, null=True, max_length=500)
    location = models.CharField(max_length=100, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    pronouns = models.CharField(max_length=50, blank=True, null=True)
    
    # Contact Information
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    country_code = models.CharField(max_length=5, blank=True, null=True, default='+1')
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
    timezone = models.CharField(max_length=50, blank=True, null=True, default='UTC')
    language_preference = models.CharField(max_length=10, blank=True, null=True, default='en')
    currency_preference = models.CharField(max_length=3, blank=True, null=True, default='USD')
    
    # Account Settings
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='personal')
    profile_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    
    # Verification & Status
    is_verified = models.BooleanField(default=False)
    is_verified_seller = models.BooleanField(default=False)
    seller_type = models.CharField(max_length=50, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile_completion_percentage = models.IntegerField(default=0)
    
    # Marketing Preferences
    marketing_emails_enabled = models.BooleanField(default=True)
    newsletter_enabled = models.BooleanField(default=True)
    notifications_enabled = models.BooleanField(default=True)

    def calculate_profile_completion(self):
        """Calculate profile completion percentage"""
        import logging
        logger = logging.getLogger(__name__)
        
        fields_to_check = [
            'bio', 'location', 'birth_date', 'phone_number', 'job_title',
            'company', 'city', 'country'
        ]
        
        completed_fields = []
        empty_fields = []
        
        for field in fields_to_check:
            field_value = getattr(self, field)
            if field_value:
                completed_fields.append(field)
            else:
                empty_fields.append(field)
        
        old_percentage = self.profile_completion_percentage
        self.profile_completion_percentage = int((len(completed_fields) / len(fields_to_check)) * 100)
        
        logger.info(f"Profile completion calculation for user {self.user.username}:")
        logger.info(f"  Completed fields ({len(completed_fields)}/{len(fields_to_check)}): {completed_fields}")
        logger.info(f"  Empty fields: {empty_fields}")
        logger.info(f"  Completion: {old_percentage}% → {self.profile_completion_percentage}%")
        
        return self.profile_completion_percentage

    def save(self, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Saving profile for user {self.user.username} (Profile ID: {self.id})")
        
        old_completion = self.profile_completion_percentage
        self.calculate_profile_completion()
        
        logger.info(f"Profile completion updated: {old_completion}% → {self.profile_completion_percentage}%")
        
        super().save(*args, **kwargs)
        logger.info("Profile saved successfully to database")

    def __str__(self):
        return f'{self.user.username}\'s Profile'

@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


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
        ('order_receipt', 'Order Receipt'),
        ('order_status_update', 'Order Status Update'),
        ('order_cancellation', 'Order Cancellation'),
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
