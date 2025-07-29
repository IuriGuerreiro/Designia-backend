import os
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import EmailVerificationToken, TwoFactorCode, EmailRequestAttempt


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def check_unused_codes_exist(user, request_type, purpose=None):
    """
    Check if there are unused codes/tokens for the user
    Returns True if unused codes exist
    """
    if request_type == 'email_verification':
        # Check for unused email verification tokens
        return EmailVerificationToken.objects.filter(
            user=user,
            is_used=False,
            expires_at__gt=timezone.now()
        ).exists()
        
    elif request_type == 'two_factor_code':
        # Check for unused 2FA codes for specific purpose if provided
        filter_kwargs = {
            'user': user,
            'is_used': False,
            'expires_at__gt': timezone.now()
        }
        
        if purpose:
            filter_kwargs['purpose'] = purpose
        else:
            # For general 2FA codes, exclude password reset
            filter_kwargs['purpose__in'] = ['enable_2fa', 'disable_2fa', 'login', 'set_password']
            
        return TwoFactorCode.objects.filter(**filter_kwargs).exists()
        
    elif request_type == 'password_reset':
        # For password reset, check for unused 2FA codes with reset_password purpose
        return TwoFactorCode.objects.filter(
            user=user,
            purpose='reset_password',
            is_used=False,
            expires_at__gt=timezone.now()
        ).exists()
    
    return False


def check_email_rate_limit(user, email, request_type, request=None, purpose=None):
    """
    Check if user has exceeded the rate limit for email requests
    Only applies rate limit if there are unused codes/tokens
    Returns (can_send, time_remaining_seconds)
    """
    # First check if there are any unused codes/tokens
    has_unused_codes = check_unused_codes_exist(user, request_type, purpose)
    
    # If no unused codes, allow immediate sending
    if not has_unused_codes:
        return True, 0
    
    # If there are unused codes, apply rate limiting
    one_minute_ago = timezone.now() - timedelta(minutes=1)
    
    # Check recent attempts by user and request type
    recent_attempts = EmailRequestAttempt.objects.filter(
        user=user,
        request_type=request_type,
        created_at__gte=one_minute_ago
    )
    
    if recent_attempts.exists():
        # Calculate time remaining
        latest_attempt = recent_attempts.order_by('-created_at').first()
        time_since_last = timezone.now() - latest_attempt.created_at
        time_remaining = timedelta(minutes=1) - time_since_last
        time_remaining_seconds = int(time_remaining.total_seconds())
        
        return False, max(0, time_remaining_seconds)
    
    return True, 0


def get_email_rate_limit_status(user, email, request_type, purpose=None):
    """
    Get the current rate limit status for a user and request type
    Returns (can_send, time_remaining_seconds)
    """
    return check_email_rate_limit(user, email, request_type, None, purpose)


def record_email_attempt(user, email, request_type, request=None):
    """Record an email attempt for rate limiting"""
    ip_address = get_client_ip(request) if request else None
    
    EmailRequestAttempt.objects.create(
        user=user,
        email=email,
        request_type=request_type,
        ip_address=ip_address
    )


def send_verification_email(user, request):
    """Send email verification email to user (prints to console for development)"""
    # Check rate limit
    can_send, time_remaining = check_email_rate_limit(user, user.email, 'email_verification', request)
    if not can_send:
        return False, f"Please wait {time_remaining} seconds before requesting another verification email."
    
    # Record the attempt
    record_email_attempt(user, user.email, 'email_verification', request)
    
    # Create verification token
    token = EmailVerificationToken.objects.create(user=user)
    
    # Build verification URL
    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    verification_url = f"{frontend_url}/verify-email/{token.token}"
    
    # Print verification details to console
    print("\n" + "="*80)
    print("🔐 EMAIL VERIFICATION CODE")
    print("="*80)
    print(f"📧 User: {user.email}")
    print(f"👤 Name: {user.first_name or user.username}")
    print(f"🔗 Verification URL: {verification_url}")
    print(f"🎫 Token: {token.token}")
    print(f"⏰ Expires: {token.expires_at}")
    print("="*80)
    print("📱 To verify: Copy the URL above and paste it in your browser")
    print("="*80 + "\n")
    
    # For development, we always return True since we're printing to console
    return True, "Verification email sent successfully"


def verify_email_token(token_str):
    """Verify email token and activate user"""
    try:
        token = EmailVerificationToken.objects.get(token=token_str, is_used=False)
        
        if token.is_expired():
            return False, "Token has expired"
        
        # Mark token as used
        token.is_used = True
        token.save()
        
        # Activate user
        user = token.user
        user.is_email_verified = True
        user.is_active = True
        user.save()
        
        return True, "Email verified successfully"
        
    except EmailVerificationToken.DoesNotExist:
        return False, "Invalid or expired token"


def send_2fa_code(user, purpose='enable_2fa', request=None):
    """Send 2FA code to user email (prints to console for development)"""
    # For 2FA codes, use purpose-specific rate limiting
    request_type = 'password_reset' if purpose == 'reset_password' else 'two_factor_code'
    
    # Check rate limit for this specific type and purpose
    can_send, time_remaining = check_email_rate_limit(user, user.email, request_type, request, purpose)
    if not can_send:
        return False, f"Please wait {time_remaining} seconds before requesting another code."
    
    # Record the attempt
    record_email_attempt(user, user.email, request_type, request)
    
    # Invalidate any existing unused codes for this user and purpose
    TwoFactorCode.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    
    # Create new 2FA code
    two_fa_code = TwoFactorCode.objects.create(user=user, purpose=purpose)
    
    # Print 2FA code to console
    print("\n" + "="*80)
    print("🔐 TWO-FACTOR AUTHENTICATION CODE")
    print("="*80)
    print(f"📧 User: {user.email}")
    print(f"👤 Name: {user.first_name or user.username}")
    print(f"🔢 2FA Code: {two_fa_code.code}")
    print(f"🎯 Purpose: {purpose}")
    print(f"⏰ Expires: {two_fa_code.expires_at}")
    print("="*80)
    print("📱 Enter this 6-digit code in your app to continue")
    print("="*80 + "\n")
    
    # For development, we always return True since we're printing to console
    return True, two_fa_code.code


def verify_2fa_code(user, code, purpose='enable_2fa'):
    """Verify 2FA code for user"""
    try:
        two_fa_code = TwoFactorCode.objects.get(
            user=user, 
            code=code, 
            purpose=purpose,
            is_used=False
        )
        
        if not two_fa_code.is_valid():
            return False, "Code has expired or is invalid"
        
        # Mark code as used
        two_fa_code.is_used = True
        two_fa_code.save()
        
        return True, "Code verified successfully"
        
    except TwoFactorCode.DoesNotExist:
        return False, "Invalid or expired code"