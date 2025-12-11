"""
Django Email Provider implementation.

Wraps existing email sending logic from authentication.utils and utils.email_utils.
Preserves all rate limiting, template rendering, and email sending behavior.
"""

from typing import Optional, Tuple

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from authentication.models import EmailVerificationToken, TwoFactorCode
from authentication.utils import check_email_rate_limit, record_email_attempt as utils_record_email_attempt
from utils.email_utils import send_email

from .email_interface import EmailProvider


class DjangoEmailProvider(EmailProvider):
    """
    Production email provider using Django's email backend.

    Wraps existing authentication email utilities to provide a clean interface
    while preserving all business logic like rate limiting and template rendering.
    """

    def send_verification_email(self, user, verification_token: str, request=None) -> Tuple[bool, str]:
        """
        Send email verification email to user with HTML + text templates.

        This wraps the existing send_verification_email logic but accepts
        a token string instead of creating one internally (separation of concerns).
        """
        # Rate limiting is now handled by service layer before calling this
        # Build verification URL from settings.FRONTEND_URL
        verification_url = f"{settings.FRONTEND_URL}/verify-email/{verification_token}"

        # Get the token object for expiry time (for display in email)
        try:
            token_obj = EmailVerificationToken.objects.get(token=verification_token)
            expires_at_str = token_obj.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        except EmailVerificationToken.DoesNotExist:
            # Fallback if token not found
            expires_at_str = "24 hours"

        # Prepare context for templates
        context = {
            "user": user,
            "verification_url": verification_url,
            "expires_at": expires_at_str,
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

    def send_2fa_code(self, user, code: str, purpose: str, request=None) -> Tuple[bool, str]:
        """
        Send 2FA code to user email using HTML + text templates.

        Preserves existing template rendering logic from authentication.utils.
        """
        # Template context
        purpose_readable = purpose.replace("_", " ")
        context = {
            "user": user,
            "code": code,
            "purpose": purpose,
            "purpose_readable": purpose_readable,
            "current_year": timezone.now().year,
        }

        # Try to get expiry time from code object
        try:
            code_obj = TwoFactorCode.objects.get(user=user, code=code, is_used=False)
            context["expires_at"] = code_obj.expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        except TwoFactorCode.DoesNotExist:
            # Fallback expiry display
            context["expires_at"] = "10 minutes"

        subject = f"Your Designia verification code: {code}"
        html_message = render_to_string("authentication/emails/two_factor_code.html", context)
        text_message = render_to_string("authentication/emails/two_factor_code.txt", context)

        ok, info = send_email(
            subject=subject,
            message=text_message,
            recipient_list=[user.email],
            html_message=html_message,
        )
        return (True, "2FA code sent successfully") if ok else (False, info)

    def check_rate_limit(self, user, email: str, request_type: str, purpose: Optional[str] = None) -> Tuple[bool, int]:
        """
        Check if user can send email (rate limiting).

        Delegates to existing authentication.utils.check_email_rate_limit.
        """
        return check_email_rate_limit(user, email, request_type, request=None, purpose=purpose)

    def record_email_attempt(self, user, email: str, request_type: str, request=None) -> None:
        """
        Record email attempt for rate limiting.

        Delegates to existing authentication.utils.record_email_attempt.
        """
        utils_record_email_attempt(user, email, request_type, request)
