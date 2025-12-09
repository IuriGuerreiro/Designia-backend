"""
Abstract Email Provider interface following Dependency Inversion Principle.

This interface decouples business logic from email infrastructure,
making code testable and allowing different email backend implementations.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class EmailProvider(ABC):
    """Abstract email provider interface for authentication emails."""

    @abstractmethod
    def send_verification_email(self, user, verification_token: str, request=None) -> Tuple[bool, str]:
        """
        Send email verification link to user.

        Args:
            user: CustomUser instance
            verification_token: EmailVerificationToken token string
            request: Optional Django request for IP tracking

        Returns:
            (success: bool, message: str)
        """
        pass

    @abstractmethod
    def send_2fa_code(self, user, code: str, purpose: str, request=None) -> Tuple[bool, str]:
        """
        Send 2FA verification code to user.

        Args:
            user: CustomUser instance
            code: Generated 2FA code
            purpose: Purpose of 2FA code (login, enable_2fa, disable_2fa, etc.)
            request: Optional Django request for IP tracking

        Returns:
            (success: bool, message: str)
        """
        pass

    @abstractmethod
    def check_rate_limit(self, user, email: str, request_type: str, purpose: Optional[str] = None) -> Tuple[bool, int]:
        """
        Check if user can send email (rate limiting).

        Args:
            user: CustomUser instance
            email: Email address
            request_type: Type of email (email_verification, two_factor_code, password_reset)
            purpose: Optional purpose for 2FA codes

        Returns:
            (can_send: bool, time_remaining_seconds: int)
        """
        pass

    @abstractmethod
    def record_email_attempt(self, user, email: str, request_type: str, request=None) -> None:
        """
        Record email attempt for rate limiting.

        Args:
            user: CustomUser instance
            email: Email address
            request_type: Type of email
            request: Optional Django request for IP tracking
        """
        pass
