from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.api.serializers import (
    TwoFactorCodeRequestSerializer,
    TwoFactorConfirmSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)
from authentication.api.serializers.response_serializers import (
    AccountStatusResponseSerializer,
    ErrorResponseSerializer,
    GoogleLoginRequestSerializer,
    Login2FAResponseSerializer,
    LoginRequestSerializer,
    LoginResponseSerializer,
    RegisterResponseSerializer,
    ResendVerificationRequestSerializer,
    ResendVerificationResponseSerializer,
    TwoFactorVerifyRequestSerializer,
    VerifyEmailRequestSerializer,
    VerifyEmailResponseSerializer,
)
from authentication.domain.services.auth_service import AuthService
from authentication.infra.auth_providers.google import GoogleAuthProvider
from authentication.infra.mail.django_email_provider import DjangoEmailProvider


# Dependency Injection Helper
def get_auth_service():
    """Factory to get AuthService instance with dependencies."""
    return AuthService(email_provider=DjangoEmailProvider(), google_provider=GoogleAuthProvider())


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_login",
        summary="Login with email and password",
        description="""
        Authenticate user with email and password.

        **Flow:**
        1. If user has 2FA disabled → Returns JWT tokens immediately
        2. If user has 2FA enabled → Returns `requires_2fa: true` with user_id for verification

        **Rate Limiting:** 5 requests/minute per IP (if Kong Gateway enabled)
        """,
        request=LoginRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=LoginResponseSerializer,
                description="Login successful (no 2FA required)",
                examples=[
                    OpenApiExample(
                        "Successful Login",
                        value={
                            "message": "Login successful",
                            "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                            "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                            "user": {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "email": "user@example.com",
                                "username": "johndoe",
                                "role": "customer",
                            },
                        },
                    )
                ],
            ),
            202: OpenApiResponse(
                response=Login2FAResponseSerializer,
                description="2FA verification required",
                examples=[
                    OpenApiExample(
                        "2FA Required",
                        value={
                            "requires_2fa": True,
                            "message": "2FA code sent to your email",
                            "user_id": "123e4567-e89b-12d3-a456-426614174000",
                            "code_already_sent": False,
                        },
                    )
                ],
            ),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid credentials"),
            403: OpenApiResponse(
                response=ErrorResponseSerializer, description="Email not verified or account disabled"
            ),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        service = get_auth_service()
        result = service.login(email, password, request)

        if result.success:
            if result.requires_2fa:
                return Response(
                    {
                        "requires_2fa": True,
                        "message": result.message,
                        "user_id": result.user_id,
                        "code_already_sent": result.code_already_sent,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "message": result.message,
                    "access": result.access_token,
                    "refresh": result.refresh_token,
                    "user": UserSerializer(result.user).data,
                },
                status=status.HTTP_200_OK,
            )

        # Handle errors
        if result.data and result.data.get("warning_type"):
            # Specific warning (e.g. email verification)
            return Response({"error": result.error, **result.data}, status=status.HTTP_403_FORBIDDEN)

        return Response({"error": result.error}, status=status.HTTP_401_UNAUTHORIZED)


class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_register",
        summary="Register new user account",
        description="""
        Create a new user account and send email verification.

        **Flow:**
        1. User submits registration form
        2. Account created (inactive until email verified)
        3. Verification email sent
        4. User must verify email before logging in

        **Rate Limiting:** 3 requests/minute per IP (if Kong Gateway enabled)
        """,
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                response=RegisterResponseSerializer,
                description="Registration successful",
                examples=[
                    OpenApiExample(
                        "Successful Registration",
                        value={
                            "message": "Registration successful. Please check your email to verify your account.",
                            "user": {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "email": "newuser@example.com",
                                "username": "newuser",
                                "is_email_verified": False,
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error (email exists, passwords don't match, etc.)",
            ),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            service = get_auth_service()
            result = service.register(
                email=serializer.validated_data["email"],
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
                first_name=serializer.validated_data.get("first_name", ""),
                last_name=serializer.validated_data.get("last_name", ""),
                request=request,
            )

            if result.success:
                return Response(
                    {"message": result.message, "user": UserSerializer(result.user).data},
                    status=status.HTTP_201_CREATED,
                )

            return Response({"error": result.error}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_verify_email",
        summary="Verify email address",
        description="""
        Verify user's email address using the token from verification email.

        **Flow:**
        1. User receives email with verification link
        2. Frontend extracts token from URL
        3. Frontend sends token to this endpoint
        4. User account activated
        """,
        request=VerifyEmailRequestSerializer,
        responses={
            200: OpenApiResponse(response=VerifyEmailResponseSerializer, description="Email verified successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid or expired token"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        token = request.data.get("token")
        service = get_auth_service()
        result = service.verify_email(token)

        if result.success:
            return Response({"message": result.message}, status=status.HTTP_200_OK)

        return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_resend_verification",
        summary="Resend verification email",
        description="""
        Resend email verification link.

        **Rate Limiting:** Can only send every 60 seconds per email.

        **Security Note:** Returns success even if email doesn't exist (prevents enumeration).
        """,
        request=ResendVerificationRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=ResendVerificationResponseSerializer,
                description="Verification email sent (or email already verified)",
            ),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Email already verified"),
            429: OpenApiResponse(response=ErrorResponseSerializer, description="Rate limited - too many requests"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Need to fetch user here or let service handle it?
        # AuthService.send_verification_email takes a USER object.
        # This implies we need to find the user first.
        from authentication.domain.models import CustomUser

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Don't reveal user existence? Or standard "if user exists sent"?
            # For now return success to prevent enumeration
            return Response(
                {"message": "If an account exists, a verification email has been sent."}, status=status.HTTP_200_OK
            )

        if user.is_email_verified:
            return Response({"message": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        service = get_auth_service()
        result = service.send_verification_email(user, request)

        if result.success:
            return Response({"message": "Verification email sent."}, status=status.HTTP_200_OK)

        return Response({"error": result.message}, status=status.HTTP_429_TOO_MANY_REQUESTS)


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_google_login",
        summary="Login with Google OAuth",
        description="""
        Authenticate using Google OAuth token.

        **Flow:**
        1. Frontend gets Google OAuth token using Google Sign-In
        2. Frontend sends token to this endpoint
        3. Backend verifies token with Google
        4. Returns JWT tokens for Designia

        **Note:** Creates new account automatically if user doesn't exist.
        """,
        request=GoogleLoginRequestSerializer,
        responses={
            200: OpenApiResponse(response=LoginResponseSerializer, description="Google login successful"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid Google token"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

        service = get_auth_service()
        result = service.google_login(token, request)

        if result.success:
            return Response(
                {
                    "message": result.message,
                    "access": result.access_token,
                    "refresh": result.refresh_token,
                    "user": UserSerializer(result.user).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response({"error": result.error}, status=status.HTTP_400_BAD_REQUEST)


class TwoFactorLoginVerifyView(APIView):
    """Verify 2FA code specifically for Login flow"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="auth_2fa_verify_login",
        summary="Verify 2FA code during login",
        description="""
        Complete login by verifying 2FA code sent to email.

        **Flow:**
        1. User logs in with email/password
        2. If 2FA enabled, receives user_id and message to check email
        3. User receives 6-digit code via email
        4. User submits code to this endpoint
        5. Returns JWT tokens on success

        **Code Validity:** Codes expire after 10 minutes.
        """,
        request=TwoFactorVerifyRequestSerializer,
        responses={
            200: OpenApiResponse(response=LoginResponseSerializer, description="2FA verified, login successful"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid or expired code"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        user_id = request.data.get("user_id")
        code = request.data.get("code")

        service = get_auth_service()
        result = service.handle_2fa_login(user_id, code, request)

        if result.success:
            return Response(
                {
                    "message": result.message,
                    "access": result.access_token,
                    "refresh": result.refresh_token,
                    "user": UserSerializer(result.user).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response({"error": result.error}, status=status.HTTP_400_BAD_REQUEST)


class Send2FACodeView(APIView):
    """Request a 2FA code for a specific purpose (enable/disable)"""

    permission_classes = [permissions.IsAuthenticated]

    # ============================================================================
    # 2FA MANAGEMENT WORKFLOW
    # ============================================================================
    #
    # The 2FA setup/teardown process is designed to be secure and prevent lockouts.
    #
    # ENABLE FLOW:
    # 1. Client requests code: POST /api/auth/2fa/send-code/ { "purpose": "enable_2fa" }
    # 2. Server checks credentials, generates code, emails it to user.
    # 3. Client submits code:  POST /api/auth/2fa/enable/ { "code": "123456" }
    # 4. Server verifies code. If valid, sets user.two_factor_enabled = True.
    #
    # DISABLE FLOW:
    # 1. Client requests code: POST /api/auth/2fa/send-code/ { "purpose": "disable_2fa" }
    #    (This step ensures a session hijacker cannot disable 2FA without email access)
    # 2. Server generates code, emails it to user.
    # 3. Client submits code:  POST /api/auth/2fa/disable/ { "code": "123456" }
    # 4. Server verifies code. If valid, sets user.two_factor_enabled = False.
    #
    # ============================================================================

    @extend_schema(
        operation_id="auth_send_2fa_code",
        summary="Send 2FA code",
        description="""
        **Step 1 of 2FA Workflow:** Initiate 2FA setup or removal.

        Sends a 6-digit verification code to the user's email address.
        This code is required to confirm the subsequent 'enable' or 'disable' action.

        **Purposes:**
        - `enable_2fa`: Request code to turn ON 2FA (verifies you can receive codes)
        - `disable_2fa`: Request code to turn OFF 2FA (security check)
        """,
        request=TwoFactorCodeRequestSerializer,
        responses={
            200: OpenApiResponse(description="Code sent successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid purpose or rate limited"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TwoFactorCodeRequestSerializer(data=request.data)
        if serializer.is_valid():
            purpose = serializer.validated_data["purpose"]
            service = get_auth_service()
            result = service.send_2fa_code(request.user, purpose, request)

            if result.success:
                return Response({"message": result.message}, status=status.HTTP_200_OK)
            return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class Enable2FAView(APIView):
    """Verify code and enable 2FA"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_enable_2fa",
        summary="Enable 2FA",
        description="""
        **Step 2 of Enable Flow:** Finalize 2FA setup.

        Verifies the code received from `send-code` endpoint.
        If successful, **Two-Factor Authentication will be activated** for this account.
        Future logins will require a verification code.
        """,
        request=TwoFactorConfirmSerializer,
        responses={
            200: OpenApiResponse(description="2FA enabled successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid code"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TwoFactorConfirmSerializer(data=request.data)
        if serializer.is_valid():
            code = serializer.validated_data["code"]
            service = get_auth_service()
            result = service.enable_2fa(request.user, code)

            if result.success:
                return Response({"message": result.message}, status=status.HTTP_200_OK)
            return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class Disable2FAView(APIView):
    """Verify code and disable 2FA"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_disable_2fa",
        summary="Disable 2FA",
        description="""
        **Step 2 of Disable Flow:** Deactivate 2FA.

        Verifies the code received from `send-code` endpoint to ensure security.
        If successful, **Two-Factor Authentication will be turned OFF**.
        """,
        request=TwoFactorConfirmSerializer,
        responses={
            200: OpenApiResponse(description="2FA disabled successfully"),
            400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid code"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TwoFactorConfirmSerializer(data=request.data)
        if serializer.is_valid():
            code = serializer.validated_data["code"]
            service = get_auth_service()
            result = service.disable_2fa(request.user, code)

            if result.success:
                return Response({"message": result.message}, status=status.HTTP_200_OK)
            return Response({"error": result.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountStatusView(APIView):
    """Check account activation status"""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_account_status",
        summary="Check account activation status",
        description="""
        Get detailed status of your account including email verification and activation status.

        **Protected:** Requires JWT authentication.

        **Returns:**
        - Account activation status
        - Email verification status
        - Whether user can login
        - 2FA status
        - User role
        - Account creation date

        **Use Cases:**
        - Frontend: Check if user needs to verify email
        - Frontend: Show activation status in profile
        - Mobile: Determine if user can access protected features
        """,
        responses={
            200: OpenApiResponse(
                response=AccountStatusResponseSerializer,
                description="Account status retrieved",
                examples=[
                    OpenApiExample(
                        "Verified Account",
                        value={
                            "is_active": True,
                            "is_email_verified": True,
                            "email": "user@example.com",
                            "can_login": True,
                            "two_factor_enabled": False,
                            "role": "customer",
                            "account_created": "2025-01-15T10:30:00Z",
                        },
                    ),
                    OpenApiExample(
                        "Unverified Account",
                        value={
                            "is_active": False,
                            "is_email_verified": False,
                            "email": "newuser@example.com",
                            "can_login": False,
                            "two_factor_enabled": False,
                            "role": "customer",
                            "account_created": "2025-01-20T14:22:00Z",
                        },
                    ),
                    OpenApiExample(
                        "Verified Seller with 2FA",
                        value={
                            "is_active": True,
                            "is_email_verified": True,
                            "email": "seller@example.com",
                            "can_login": True,
                            "two_factor_enabled": True,
                            "role": "seller",
                            "account_created": "2024-12-01T08:15:00Z",
                        },
                    ),
                ],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer, description="Unauthorized - no valid JWT token provided"
            ),
        },
        tags=["Authentication"],
    )
    def get(self, request):
        """Get account status for authenticated user"""
        user = request.user

        # Calculate if user can login
        can_login = user.is_active and user.is_email_verified

        return Response(
            {
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
                "email": user.email,
                "can_login": can_login,
                "two_factor_enabled": user.two_factor_enabled,
                "role": user.role,
                "account_created": user.date_joined,
            },
            status=status.HTTP_200_OK,
        )
