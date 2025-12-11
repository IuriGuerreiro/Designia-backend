"""
Response Serializers for API Documentation

These serializers define the structure of API responses for OpenAPI schema generation.
They are NOT used for data validation, only for documentation in Swagger/ReDoc.
"""

from rest_framework import serializers

from .auth_serializers import UserSerializer


# ===== Authentication Response Serializers =====


class LoginResponseSerializer(serializers.Serializer):
    """Response for successful login (no 2FA)"""

    message = serializers.CharField(help_text="Success message")
    access = serializers.CharField(help_text="JWT access token")
    refresh = serializers.CharField(help_text="JWT refresh token")
    user = UserSerializer(help_text="User details")


class Login2FAResponseSerializer(serializers.Serializer):
    """Response for login requiring 2FA verification"""

    requires_2fa = serializers.BooleanField(help_text="Whether 2FA is required", default=True)
    message = serializers.CharField(help_text="Instruction message")
    user_id = serializers.CharField(help_text="User ID for 2FA verification")
    code_already_sent = serializers.BooleanField(
        help_text="Whether an unused 2FA code was already sent", default=False
    )


class LoginRequestSerializer(serializers.Serializer):
    """Request body for login"""

    email = serializers.EmailField(help_text="User's email address")
    password = serializers.CharField(write_only=True, style={"input_type": "password"}, help_text="User's password")


class RegisterResponseSerializer(serializers.Serializer):
    """Response for successful registration"""

    message = serializers.CharField(help_text="Success message with instructions")
    user = UserSerializer(help_text="Newly registered user details")


class VerifyEmailRequestSerializer(serializers.Serializer):
    """Request body for email verification"""

    token = serializers.CharField(help_text="Email verification token from email link")


class VerifyEmailResponseSerializer(serializers.Serializer):
    """Response for email verification"""

    message = serializers.CharField(help_text="Success message")


class ResendVerificationRequestSerializer(serializers.Serializer):
    """Request body for resending verification email"""

    email = serializers.EmailField(help_text="Email address to resend verification to")


class ResendVerificationResponseSerializer(serializers.Serializer):
    """Response for resending verification email"""

    message = serializers.CharField(help_text="Status message")


class GoogleLoginRequestSerializer(serializers.Serializer):
    """Request body for Google OAuth login"""

    token = serializers.CharField(help_text="Google OAuth token from frontend")


class TwoFactorVerifyRequestSerializer(serializers.Serializer):
    """Request body for 2FA verification during login"""

    user_id = serializers.CharField(help_text="User ID from initial login response")
    code = serializers.CharField(max_length=6, min_length=6, help_text="6-digit 2FA code sent to email")


# ===== Seller Response Serializers =====


class SellerApplicationSubmitResponseSerializer(serializers.Serializer):
    """Response for seller application submission"""

    message = serializers.CharField(help_text="Success message")
    application_id = serializers.IntegerField(help_text="ID of created/updated application")
    images_uploaded = serializers.IntegerField(help_text="Number of workshop images uploaded")


class SellerApplicationStatusResponseSerializer(serializers.Serializer):
    """Response for seller application status check"""

    has_application = serializers.BooleanField(help_text="Whether user has an application")
    is_seller = serializers.BooleanField(help_text="Whether user is already a seller")
    status = serializers.CharField(
        help_text="Application status: pending, approved, rejected, or none", allow_null=True
    )
    application_id = serializers.IntegerField(help_text="Application ID if exists", allow_null=True)
    submitted_at = serializers.DateTimeField(help_text="Submission timestamp", allow_null=True)
    admin_notes = serializers.CharField(help_text="Admin notes/feedback", allow_blank=True, allow_null=True)
    rejection_reason = serializers.CharField(
        help_text="Reason for rejection if rejected", allow_blank=True, allow_null=True
    )


class SellerApplicationAdminActionRequestSerializer(serializers.Serializer):
    """Request body for admin approve/reject action"""

    action = serializers.ChoiceField(choices=["approve", "reject"], help_text="Action to perform: approve or reject")
    reason = serializers.CharField(
        help_text="Reason for rejection (required if action=reject)", required=False, allow_blank=True
    )


class SellerApplicationAdminActionResponseSerializer(serializers.Serializer):
    """Response for admin approve/reject action"""

    message = serializers.CharField(help_text="Success message")
    user_id = serializers.CharField(help_text="ID of the user", required=False)
    user_email = serializers.EmailField(help_text="Email of the user", required=False)


# ===== Profile Response Serializers =====


class ProfileUpdateResponseSerializer(serializers.Serializer):
    """Response for profile update (returns full ProfileSerializer)"""

    # This will be replaced by ProfileSerializer in the actual view
    # but we define it here for consistency
    message = serializers.CharField(help_text="Success message", required=False)


class ProfilePictureUploadResponseSerializer(serializers.Serializer):
    """Response for profile picture upload"""

    message = serializers.CharField(help_text="Success message", required=False)
    profile_picture_url = serializers.CharField(help_text="S3 key/path of uploaded image")
    profile_picture_temp_url = serializers.URLField(help_text="Temporary presigned URL for immediate display")
    size = serializers.IntegerField(help_text="File size in bytes")
    content_type = serializers.CharField(help_text="MIME type of uploaded file")


class ProfilePictureDeleteResponseSerializer(serializers.Serializer):
    """Response for profile picture deletion"""

    message = serializers.CharField(help_text="Success message")


class AccountStatusResponseSerializer(serializers.Serializer):
    """Response for account status check"""

    is_active = serializers.BooleanField(help_text="Whether the account is active")
    is_email_verified = serializers.BooleanField(help_text="Whether email is verified")
    email = serializers.EmailField(help_text="User's email address")
    can_login = serializers.BooleanField(help_text="Whether user can login (active + email verified)")
    two_factor_enabled = serializers.BooleanField(help_text="Whether 2FA is enabled")
    role = serializers.CharField(help_text="User role: customer, seller, or admin")
    account_created = serializers.DateTimeField(help_text="When account was created")


# ===== Generic Error Response Serializers =====


class ErrorResponseSerializer(serializers.Serializer):
    """Standard error response"""

    error = serializers.CharField(help_text="Error message")
    details = serializers.DictField(help_text="Additional error details", required=False, allow_null=True)


class ValidationErrorResponseSerializer(serializers.Serializer):
    """Validation error response (DRF standard)"""

    field_name = serializers.ListField(
        child=serializers.CharField(), help_text="List of error messages for each invalid field"
    )

    class Meta:
        # This is a placeholder - actual validation errors vary by field
        ref_name = "ValidationError"
