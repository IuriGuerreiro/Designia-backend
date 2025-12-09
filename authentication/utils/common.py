from datetime import timedelta

from django.utils import timezone

from authentication.domain.models import EmailRequestAttempt, EmailVerificationToken, TwoFactorCode


def get_client_ip(request):
    """Get client IP address from request"""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def check_unused_codes_exist(user, request_type, purpose=None):
    """
    Check if there are unused codes/tokens for the user
    Returns True if unused codes exist
    """
    if request_type == "email_verification":
        # Check for unused email verification tokens
        return EmailVerificationToken.objects.filter(user=user, is_used=False, expires_at__gt=timezone.now()).exists()

    elif request_type == "two_factor_code":
        # Check for unused 2FA codes for specific purpose if provided
        filter_kwargs = {"user": user, "is_used": False, "expires_at__gt=timezone.now()": True}
        # FIX: The above kwarg is wrong (typo from move?), let's fix it properly
        filter_kwargs = {"user": user, "is_used": False, "expires_at__gt": timezone.now()}

        if purpose:
            filter_kwargs["purpose"] = purpose
        else:
            # For general 2FA codes, exclude password reset
            filter_kwargs["purpose__in"] = ["enable_2fa", "disable_2fa", "login", "set_password"]

        return TwoFactorCode.objects.filter(**filter_kwargs).exists()

    elif request_type == "password_reset":
        # For password reset, check for unused 2FA codes with reset_password purpose
        return TwoFactorCode.objects.filter(
            user=user, purpose="reset_password", is_used=False, expires_at__gt=timezone.now()
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
        user=user, request_type=request_type, created_at__gte=one_minute_ago
    )

    if recent_attempts.exists():
        # Calculate time remaining
        latest_attempt = recent_attempts.order_by("-created_at").first()
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
    EmailRequestAttempt.objects.create(user=user, email=email, request_type=request_type, ip_address=ip_address)


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


def verify_2fa_code(user, code, purpose="enable_2fa"):
    """Verify 2FA code for user"""
    try:
        two_fa_code = TwoFactorCode.objects.get(user=user, code=code, purpose=purpose, is_used=False)

        if not two_fa_code.is_valid():
            return False, "Code has expired or is invalid"

        # Mark code as used
        two_fa_code.is_used = True
        two_fa_code.save()

        return True, "Code verified successfully"

    except TwoFactorCode.DoesNotExist:
        return False, "Invalid or expired code"
