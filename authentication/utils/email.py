from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from authentication.domain.models import EmailVerificationToken, TwoFactorCode
from utils.email_utils import send_email

from .common import check_email_rate_limit, record_email_attempt


def send_verification_email(user, request):
    """Send email verification email to user with HTML + text templates."""
    # Check rate limit
    can_send, time_remaining = check_email_rate_limit(user, user.email, "email_verification", request)
    if not can_send:
        return False, f"Please wait {time_remaining} seconds before requesting another verification email."

    # Record the attempt
    record_email_attempt(user, user.email, "email_verification", request)

    # Create verification token
    token = EmailVerificationToken.objects.create(user=user)

    # Build verification URL from settings.FRONTEND_URL

    verification_url = f"{settings.FRONTEND_URL}/verify-email/{token.token}"

    # Prepare context for templates
    context = {
        "user": user,
        "verification_url": verification_url,
        "expires_at": token.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "current_year": timezone.now().year,
    }

    subject = "Verify your email address - Designia"
    html_message = render_to_string("authentication/emails/verification_email.html", context)
    text_message = render_to_string("authentication/emails/verification_email.txt", context)

    ok, info = send_email(
        subject=subject,
        message=text_message,
        recipient_list=[user.email],
        html_message=html_message,
    )
    return (True, "Verification email sent successfully") if ok else (False, info)


def send_2fa_code(user, purpose="enable_2fa", request=None):
    """Send 2FA code to user email using HTML + text templates via shared util."""
    # For 2FA codes, use purpose-specific rate limiting
    request_type = "password_reset" if purpose == "reset_password" else "two_factor_code"

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

    # Template context
    purpose_readable = purpose.replace("_", " ")
    context = {
        "user": user,
        "code": two_fa_code.code,
        "purpose": purpose,
        "purpose_readable": purpose_readable,
        "expires_at": two_fa_code.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "current_year": timezone.now().year,
    }

    subject = f"Your Designia verification code: {two_fa_code.code}"
    html_message = render_to_string("authentication/emails/two_factor_code.html", context)
    text_message = render_to_string("authentication/emails/two_factor_code.txt", context)

    ok, info = send_email(
        subject=subject,
        message=text_message,
        recipient_list=[user.email],
        html_message=html_message,
    )
    return (True, two_fa_code.code) if ok else (False, info)
