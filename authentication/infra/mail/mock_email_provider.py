"""
Mock Email Provider for testing.

Allows unit tests to verify email sending without actually sending emails.
Tracks all email attempts for test assertions.
"""

from typing import Any, Dict, List, Optional, Tuple


class MockEmailProvider:
    """
    Mock email provider for testing.

    Stores all email attempts in memory for test assertions.
    Never actually sends emails.
    """

    def __init__(self):
        """Initialize mock with empty tracking lists."""
        self.verification_emails_sent: List[Dict[str, Any]] = []
        self.twofa_codes_sent: List[Dict[str, Any]] = []
        self.rate_limit_checks: List[Dict[str, Any]] = []
        self.email_attempts_recorded: List[Dict[str, Any]] = []

        # Mock rate limit behavior (default: allow all)
        self.should_rate_limit = False
        self.rate_limit_seconds = 60

    def send_verification_email(self, user, verification_token: str, request=None) -> Tuple[bool, str]:
        """
        Mock sending verification email.

        Stores email details for test assertions.
        """
        self.verification_emails_sent.append(
            {
                "user": user,
                "user_email": user.email,
                "token": verification_token,
                "request": request,
            }
        )
        return True, "Verification email sent successfully"

    def send_2fa_code(self, user, code: str, purpose: str, request=None) -> Tuple[bool, str]:
        """
        Mock sending 2FA code.

        Stores code details for test assertions.
        """
        self.twofa_codes_sent.append(
            {
                "user": user,
                "user_email": user.email,
                "code": code,
                "purpose": purpose,
                "request": request,
            }
        )
        return True, "2FA code sent successfully"

    def check_rate_limit(self, user, email: str, request_type: str, purpose: Optional[str] = None) -> Tuple[bool, int]:
        """
        Mock rate limit checking.

        Returns configurable rate limit status.
        """
        self.rate_limit_checks.append(
            {
                "user": user,
                "email": email,
                "request_type": request_type,
                "purpose": purpose,
            }
        )

        if self.should_rate_limit:
            return False, self.rate_limit_seconds
        return True, 0

    def record_email_attempt(self, user, email: str, request_type: str, request=None) -> None:
        """
        Mock recording email attempt.

        Stores attempt details for test assertions.
        """
        self.email_attempts_recorded.append(
            {
                "user": user,
                "email": email,
                "request_type": request_type,
                "request": request,
            }
        )

    # Test helper methods
    def reset(self):
        """Clear all tracked emails and attempts."""
        self.verification_emails_sent.clear()
        self.twofa_codes_sent.clear()
        self.rate_limit_checks.clear()
        self.email_attempts_recorded.clear()

    def set_rate_limit(self, should_limit: bool, seconds: int = 60):
        """Configure mock rate limiting behavior."""
        self.should_rate_limit = should_limit
        self.rate_limit_seconds = seconds

    def get_last_verification_email(self) -> Optional[Dict[str, Any]]:
        """Get last verification email sent."""
        return self.verification_emails_sent[-1] if self.verification_emails_sent else None

    def get_last_2fa_code(self) -> Optional[Dict[str, Any]]:
        """Get last 2FA code sent."""
        return self.twofa_codes_sent[-1] if self.twofa_codes_sent else None
