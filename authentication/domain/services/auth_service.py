"""
AuthService - Core Authentication Business Logic.

Extracts all authentication business logic from views into a testable,
reusable service layer. Coordinates between email infrastructure and domain models.
"""

import logging
from typing import Optional

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction

from authentication.api.serializers.jwt_serializers import CustomRefreshToken
from authentication.domain.events import EventDispatcher
from authentication.infra.auth_providers.base import AuthProvider
from authentication.infra.mail import EmailProvider
from authentication.models import EmailVerificationToken, TwoFactorCode
from authentication.utils import (
    check_unused_codes_exist,
    verify_2fa_code as utils_verify_2fa_code,
    verify_email_token as utils_verify_email_token,
)

from .results import LoginResult, RegisterResult, Result


User = get_user_model()
logger = logging.getLogger(__name__)


class AuthService:
    """
    Authentication service encapsulating all auth business logic.

    Handles login, registration, email verification, 2FA, and Social Auth flows.
    """

    def __init__(self, email_provider: EmailProvider, google_provider: Optional[AuthProvider] = None):
        """
        Initialize AuthService with injected dependencies.

        Args:
            email_provider: Email provider implementation
            google_provider: Optional Google auth provider implementation
        """
        self.email_provider = email_provider
        self.google_provider = google_provider

    def login(self, email: str, password: str, request=None) -> LoginResult:
        """
        Authenticate user with email/password.

        Business Logic:
        1. Check if user exists
        2. Verify password
        3. Check email verification status
        4. Handle 2FA if enabled (send code or use existing)
        5. Generate JWT tokens if no 2FA

        Args:
            email: User email address
            password: User password
            request: Optional Django request for IP tracking

        Returns:
            LoginResult with authentication status and tokens
        """
        try:
            # Input validation
            if not email or not password:
                return LoginResult(success=False, error="Email and password are required.")

            # Check if user exists
            try:
                user_exists = User.objects.get(email=email)
            except User.DoesNotExist:
                EventDispatcher.dispatch_user_login_failed(
                    email=email, reason="user_not_found", ip_address=self._get_client_ip(request)
                )
                return LoginResult(success=False, error="No account found with this email address.")

            # Verify password (check manually for unverified users since authenticate requires is_active=True)
            if not user_exists.check_password(password):
                EventDispatcher.dispatch_user_login_failed(
                    email=email, reason="wrong_password", ip_address=self._get_client_ip(request)
                )
                return LoginResult(success=False, error="Incorrect password. Please try again.")

            # Check email verification
            if not user_exists.is_email_verified:
                return LoginResult(
                    success=False,
                    error="Please verify your email address before logging in.",
                    message="Account access is restricted until email verification is complete.",
                    data={
                        "email_verified": False,
                        "warning_type": "email_verification_required",
                        "user_email": user_exists.email,
                        "action_required": "verify_email",
                    },
                )

            # Password correct and email verified - authenticate
            user = authenticate(username=email, password=password)

            if not user:
                EventDispatcher.dispatch_user_login_failed(
                    email=email, reason="authentication_backend_failure", ip_address=self._get_client_ip(request)
                )
                return LoginResult(success=False, error="Authentication failed. Please try again.")

            # Check if 2FA is enabled
            if user.two_factor_enabled:
                # Dispatch "partial" success indicating 2FA is next
                EventDispatcher.dispatch_user_login_successful(
                    user=user, ip_address=self._get_client_ip(request), required_2fa=True
                )
                return self._handle_2fa_login(user, request)

            # No 2FA - dispatch full success
            EventDispatcher.dispatch_user_login_successful(
                user=user, ip_address=self._get_client_ip(request), required_2fa=False
            )

            # Generate tokens and return
            return self._generate_login_tokens(user)

        except Exception as e:
            logger.exception(f"Login error for email {email}: {e}")
            return LoginResult(success=False, error="An unexpected error occurred. Please try again later.")

    def _handle_2fa_login(self, user, request=None) -> LoginResult:
        """
        Handle 2FA challenge for login.

        Checks if unused code exists, otherwise sends new code.
        """
        # Check if there's already an unused 2FA code for login
        has_unused_code = check_unused_codes_exist(user, "two_factor_code", "login")

        if has_unused_code:
            # User already has an unused 2FA code
            return LoginResult(
                success=True,
                requires_2fa=True,
                code_already_sent=True,
                user_id=str(user.id),
                message="Two-factor authentication required. Please enter the verification code sent to your email.",
            )

        # No unused code - send new one
        can_send, time_remaining = self.email_provider.check_rate_limit(user, user.email, "two_factor_code", "login")

        if not can_send:
            return LoginResult(
                success=False, error=f"Please wait {time_remaining} seconds before requesting another code."
            )

        # Create and send 2FA code
        try:
            # Invalidate existing unused codes
            TwoFactorCode.objects.filter(user=user, purpose="login", is_used=False).update(is_used=True)

            # Create new code
            two_fa_code = TwoFactorCode.objects.create(user=user, purpose="login")

            # Record email attempt
            self.email_provider.record_email_attempt(user, user.email, "two_factor_code", request)

            # Send code
            success, message = self.email_provider.send_2fa_code(user, two_fa_code.code, "login", request)

            if not success:
                return LoginResult(success=False, error=message)

            return LoginResult(
                success=True,
                requires_2fa=True,
                code_already_sent=False,
                user_id=str(user.id),
                message="A verification code has been sent to your email.",
            )

        except Exception as e:
            logger.exception(f"Failed to send 2FA code for user {user.id}: {e}")
            return LoginResult(success=False, error="Failed to send verification code. Please try again.")

    def _generate_login_tokens(self, user) -> LoginResult:
        """Generate JWT tokens for successful login."""
        try:
            refresh = CustomRefreshToken.for_user(user)
            return LoginResult(
                success=True,
                user=user,
                access_token=str(refresh.access_token),
                refresh_token=str(refresh),
                message="Login successful",
            )
        except Exception as e:
            logger.exception(f"Token generation failed for user {user.id}: {e}")
            return LoginResult(success=False, error="Failed to generate authentication tokens.")

    def handle_2fa_login(self, user_id: str, code: str, request=None) -> LoginResult:
        """
        Complete login after 2FA verification.

        Args:
            user_id: User UUID as string
            code: 6-digit 2FA code
            request: Optional Django request for IP tracking

        Returns:
            LoginResult with tokens if verification successful
        """
        try:
            # Validate inputs
            if not user_id or not code:
                return LoginResult(success=False, error="User ID and verification code are required.")

            # Get user
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                EventDispatcher.dispatch_user_login_failed(
                    email=f"user_id_{user_id}", reason="invalid_user_id_2fa", ip_address=self._get_client_ip(request)
                )
                return LoginResult(success=False, error="Invalid user ID.")

            # Verify 2FA code
            success, message = utils_verify_2fa_code(user, code, "login")

            if not success:
                EventDispatcher.dispatch_user_login_failed(
                    email=user.email, reason="invalid_2fa_code", ip_address=self._get_client_ip(request)
                )
                return LoginResult(success=False, error=message)

            # 2FA verified - dispatch final success event
            EventDispatcher.dispatch_user_login_successful(
                user=user,
                ip_address=self._get_client_ip(request),
                required_2fa=False,  # 2FA completed
            )

            # Generate tokens
            return self._generate_login_tokens(user)

        except Exception as e:
            logger.exception(f"2FA verification error for user {user_id}: {e}")
            return LoginResult(success=False, error="An unexpected error occurred during verification.")

    def enable_2fa(self, user, code: str) -> Result:
        """
        Enable 2FA for a user.

        Verifies the code sent for 'enable_2fa' purpose.

        Args:
            user: CustomUser instance
            code: 6-digit 2FA code

        Returns:
            Result with success status
        """
        try:
            # Verify code
            success, message = utils_verify_2fa_code(user, code, "enable_2fa")

            if not success:
                return Result(success=False, message=message, error="Invalid code")

            # Enable 2FA
            user.two_factor_enabled = True
            user.save()

            # Dispatch event
            EventDispatcher.dispatch_user_2fa_enabled(user)

            return Result(success=True, message="Two-factor authentication enabled successfully.")

        except Exception as e:
            logger.exception(f"Error enabling 2FA for user {user.id}: {e}")
            return Result(success=False, message="Failed to enable 2FA.", error=str(e))

    def disable_2fa(self, user, code: str) -> Result:
        """
        Disable 2FA for a user.

        Verifies the code sent for 'disable_2fa' purpose (security check).

        Args:
            user: CustomUser instance
            code: 6-digit 2FA code

        Returns:
            Result with success status
        """
        try:
            # Verify code
            success, message = utils_verify_2fa_code(user, code, "disable_2fa")

            if not success:
                return Result(success=False, message=message, error="Invalid code")

            # Disable 2FA
            user.two_factor_enabled = False
            user.save()

            # Dispatch event
            EventDispatcher.dispatch_user_2fa_disabled(user)

            return Result(success=True, message="Two-factor authentication disabled successfully.")

        except Exception as e:
            logger.exception(f"Error disabling 2FA for user {user.id}: {e}")
            return Result(success=False, message="Failed to disable 2FA.", error=str(e))

    @transaction.atomic
    def register(
        self, email: str, username: str, password: str, first_name: str = "", last_name: str = "", request=None
    ) -> RegisterResult:
        """
        Register new user and send verification email.

        Business Logic:
        1. Validate input (handled by serializer in view layer)
        2. Create user (inactive until email verified)
        3. Send verification email
        4. Handle rate limiting

        Args:
            email: User email
            username: Username
            password: Password
            first_name: Optional first name
            last_name: Optional last name
            request: Optional Django request for IP tracking

        Returns:
            RegisterResult with user and email status
        """
        try:
            # Create user (inactive by default)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=False,  # Inactive until email verified
                is_email_verified=False,
            )

            # Send verification email
            email_result = self.send_verification_email(user, request)

            if email_result.success:
                return RegisterResult(
                    success=True,
                    user=user,
                    email_sent=True,
                    message="Registration successful! Please check your email to verify your account.",
                )
            else:
                # User created but email failed
                return RegisterResult(
                    success=True,
                    user=user,
                    email_sent=False,
                    message="Registration successful but failed to send verification email. Please contact support.",
                    error=email_result.error,
                )

        except Exception as e:
            logger.exception(f"Registration error for email {email}: {e}")
            return RegisterResult(success=False, error=str(e), message="Registration failed. Please try again.")

    def send_verification_email(self, user, request=None) -> Result:
        """
        Send or resend email verification.

        Handles rate limiting and token creation.

        Args:
            user: CustomUser instance
            request: Optional Django request for IP tracking

        Returns:
            Result with success status
        """
        try:
            # Check rate limit
            can_send, time_remaining = self.email_provider.check_rate_limit(user, user.email, "email_verification")

            if not can_send:
                return Result(
                    success=False,
                    message=f"Please wait {time_remaining} seconds before requesting another verification email.",
                    error="Rate limit exceeded",
                )

            # Record email attempt
            self.email_provider.record_email_attempt(user, user.email, "email_verification", request)

            # Create verification token
            token = EmailVerificationToken.objects.create(user=user)

            # Send email
            success, message = self.email_provider.send_verification_email(user, token.token, request)

            return Result(
                success=success,
                message=message if success else "Failed to send verification email.",
                error=None if success else message,
                data={"token": str(token.token)} if success else {},
            )

        except Exception as e:
            logger.exception(f"Failed to send verification email for user {user.id}: {e}")
            return Result(success=False, message="Failed to send verification email.", error=str(e))

    def verify_email(self, token: str) -> Result:
        """
        Verify user email with token.

        Activates user account if token is valid.

        Args:
            token: Email verification token string

        Returns:
            Result with verification status
        """
        try:
            if not token:
                return Result(success=False, message="Token is required.", error="Missing token")

            # Use existing utility function to verify token
            success, message = utils_verify_email_token(token)

            return Result(success=success, message=message, error=None if success else message)

        except Exception as e:
            logger.exception(f"Email verification error for token {token}: {e}")
            return Result(success=False, message="Verification failed. Please try again.", error=str(e))

    def send_2fa_code(self, user, purpose: str, request=None) -> Result:
        """
        Send 2FA code to user email.

        Args:
            user: CustomUser instance
            purpose: Purpose of 2FA code (login, enable_2fa, disable_2fa, etc.)
            request: Optional Django request for IP tracking

        Returns:
            Result with send status and code (for testing)
        """
        try:
            # Determine request type for rate limiting
            request_type = "password_reset" if purpose == "reset_password" else "two_factor_code"

            # Check rate limit
            can_send, time_remaining = self.email_provider.check_rate_limit(user, user.email, request_type, purpose)

            if not can_send:
                return Result(
                    success=False,
                    message=f"Please wait {time_remaining} seconds before requesting another code.",
                    error="Rate limit exceeded",
                )

            # Record email attempt
            self.email_provider.record_email_attempt(user, user.email, request_type, request)

            # Invalidate existing unused codes for this user and purpose
            TwoFactorCode.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)

            # Create new 2FA code
            two_fa_code = TwoFactorCode.objects.create(user=user, purpose=purpose)

            # Send code
            success, message = self.email_provider.send_2fa_code(user, two_fa_code.code, purpose, request)

            return Result(
                success=success,
                message=message,
                error=None if success else message,
                data={"code": two_fa_code.code} if success else {},  # Include code for testing
            )

        except Exception as e:
            logger.exception(f"Failed to send 2FA code for user {user.id}: {e}")
            return Result(success=False, message="Failed to send verification code.", error=str(e))

    def google_login(self, token: str, request=None) -> LoginResult:
        """
        Authenticate user using Google OAuth token.

        Business Logic:
        1. Verify token with Google Provider
        2. Find existing user or create new one
        3. Dispatch login event
        4. Generate JWT tokens

        Args:
            token: Google OAuth ID token
            request: Optional Django request for IP tracking/Signals

        Returns:
            LoginResult with user and tokens
        """
        if not self.google_provider:
            logger.error("Google provider not configured in AuthService")
            return LoginResult(success=False, error="Google login is not supported at this time.")

        # 1. Verify Token
        google_user_info = self.google_provider.verify_token(token)

        if not google_user_info:
            return LoginResult(success=False, error="Invalid Google token.")

        email = google_user_info.get("email")
        if not email:
            return LoginResult(success=False, error="Google token did not contain an email address.")

        try:
            # 2. Find or Create User
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=email,  # unique constraint handled by model usually, or append random if needed
                    email=email,
                    first_name=google_user_info.get("given_name", ""),
                    last_name=google_user_info.get("family_name", ""),
                    is_email_verified=True,  # Google emails are verified
                    is_active=True,
                )

                # Dispatch registration event for new Google users
                EventDispatcher.dispatch_user_registered(
                    user=user,
                    email_sent=False,  # No verification email needed
                    ip_address=self._get_client_ip(request) if request else None,
                )

            # 3. Dispatch Login Event
            EventDispatcher.dispatch_user_login_successful(
                user=user,
                ip_address=self._get_client_ip(request) if request else None,
                required_2fa=False,  # Google login bypasses 2FA usually, or can be added later
            )

            # 4. Generate Tokens
            return self._generate_login_tokens(user)

        except Exception as e:
            logger.exception(f"Google login error: {e}")
            return LoginResult(success=False, error="An unexpected error occurred during Google login.")

    def _get_client_ip(self, request) -> Optional[str]:
        """Helper to extract IP from request."""
        if not request:
            return None
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip
