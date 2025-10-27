from rest_framework import generics, status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from .jwt_serializers import CustomRefreshToken
from django.contrib.auth import authenticate
import logging
from .models import CustomUser, EmailVerificationToken, TwoFactorCode, EmailRequestAttempt
from .serializers import (
    UserRegistrationSerializer, UserSerializer, GoogleAuthSerializer, 
    TwoFactorToggleSerializer, TwoFactorVerifySerializer, 
    SetPasswordRequestSerializer, SetPasswordVerifySerializer,
    PublicUserSerializer
)
from .utils import send_verification_email, verify_email_token, send_2fa_code, verify_2fa_code, get_email_rate_limit_status
from .google_auth import GoogleAuth


logger = logging.getLogger(__name__)


def _mask_email(email: str | None) -> str | None:
    if not email:
        return None
    local, _, domain = email.partition('@')
    if not domain:
        return email
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


class PublicProfileDetailView(generics.RetrieveAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = PublicUserSerializer
    permission_classes = [AllowAny]
    lookup_field = 'pk'


class ProfileUpdateView(generics.RetrieveUpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)  # Always allow partial updates
        logger.info(
            "Profile update requested",
            extra={
                "user_id": request.user.id,
                "username": request.user.username,
                "partial": partial,
                "fields": sorted(request.data.keys()),
            },
        )

        instance = self.get_object()
        logger.debug(
            "Profile update target resolved",
            extra={"user_id": instance.id, "username": instance.username},
        )
        
        # Check if user is trying to update restricted fields without being a verified seller
        if not instance.profile.is_verified_seller:
            restricted_fields = [
                'phone_number', 'country_code', 'website', 'location',
                'job_title', 'company', 'account_type',
                'instagram_url', 'twitter_url', 'linkedin_url', 'facebook_url'
            ]
            
            # Check if any restricted fields are being updated
            profile_data = request.data.get('profile', {})
            restricted_updates = [field for field in restricted_fields if field in profile_data]

            if restricted_updates:
                logger.warning(
                    "Restricted profile fields update blocked",
                    extra={
                        "user_id": instance.id,
                        "restricted_fields": restricted_updates,
                    },
                )
                return Response({
                    'error': 'Access denied',
                    'message': 'Professional, contact, and social media fields can only be updated by verified sellers.',
                    'restricted_fields': restricted_updates
                }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        try:
            serializer.is_valid(raise_exception=True)
            logger.debug(
                "Profile serializer validation passed",
                extra={"user_id": instance.id},
            )
        except Exception as e:
            logger.error(
                "Profile serializer validation failed",
                extra={"user_id": instance.id, "errors": serializer.errors},
            )
            raise

        self.perform_update(serializer)
        logger.info(
            "Profile updated successfully",
            extra={"user_id": instance.id, "updated_fields": list(serializer.validated_data.keys())},
        )
        
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}
            logger.debug("Prefetch cache invalidated", extra={"user_id": instance.id})

        response_data = serializer.data
        return Response(response_data)


class RegistrationThrottle(SimpleRateThrottle):
    scope = "auth_register"
    rate = "5/hour"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginThrottle(SimpleRateThrottle):
    scope = "auth_login"
    rate = "10/minute"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginVerifyThrottle(SimpleRateThrottle):
    scope = "auth_login_verify"
    rate = "8/minute"

    def get_cache_key(self, request, view):
        user_id = request.data.get("user_id") if hasattr(request.data, 'get') else None
        ident = user_id or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PasswordResetRequestThrottle(SimpleRateThrottle):
    scope = "auth_password_reset_request"
    rate = "5/hour"

    def get_cache_key(self, request, view):
        email = None
        if hasattr(request, "data") and hasattr(request.data, "get"):
            email = request.data.get("email")
        ident = email or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PasswordResetVerifyThrottle(SimpleRateThrottle):
    scope = "auth_password_reset_verify"
    rate = "12/hour"

    def get_cache_key(self, request, view):
        user_id = None
        if hasattr(request, "data") and hasattr(request.data, "get"):
            user_id = request.data.get("user_id")
        ident = user_id or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class TwoFactorResendThrottle(SimpleRateThrottle):
    scope = "auth_resend_2fa"
    rate = "6/hour"

    def get_cache_key(self, request, view):
        user_id = None
        if hasattr(request, "data") and hasattr(request.data, "get"):
            user_id = request.data.get("user_id")
        ident = user_id or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AuthenticatedMutationThrottle(SimpleRateThrottle):
    scope = "auth_mutation"
    rate = "30/minute"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return self.cache_format % {"scope": self.scope, "ident": str(user.pk)}
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class TokenRefreshThrottle(SimpleRateThrottle):
    scope = "auth_token_refresh"
    rate = "30/minute"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicAuthAPIView(APIView):
    """Base class for unauthenticated authentication endpoints."""

    permission_classes = [AllowAny]
    authentication_classes = []


class RegisterView(PublicAuthAPIView):
    throttle_classes = [RegistrationThrottle]

    def post(self, request, *args, **kwargs):
        try:
            serializer = UserRegistrationSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()

                # Send verification email
                email_result = send_verification_email(user, request)

                if isinstance(email_result, tuple):
                    email_sent, message = email_result
                    if email_sent:
                        return Response({
                            'message': 'Registration successful! Please check your email to verify your account.',
                            'email': user.email,
                            'email_sent': True
                        }, status=status.HTTP_201_CREATED)
                    else:
                        # Check if it's a rate limit error or email service error
                        if "wait" in message.lower() and "seconds" in message.lower():
                            # Rate limit error
                            return Response({
                                'error': message,
                                'email': user.email,
                                'email_sent': False
                            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
                        else:
                            # Email service error - still return success since user was created
                            return Response({
                                'message': 'Registration successful but failed to send verification email. Please contact support.',
                                'email': user.email,
                                'email_sent': False
                            }, status=status.HTTP_201_CREATED)
                else:
                    # Legacy support - backwards compatibility
                    if email_result:
                        return Response({
                            'message': 'Registration successful! Please check your email to verify your account.',
                            'email': user.email,
                            'email_sent': True
                        }, status=status.HTTP_201_CREATED)
                    else:
                        return Response({
                            'message': 'Registration successful but failed to send verification email. Please contact support.',
                            'email': user.email,
                            'email_sent': False
                        }, status=status.HTTP_201_CREATED)
            else:
                # Log validation errors for debugging
                logger.error(
                    "Registration validation failed",
                    extra={
                        "remote_addr": request.META.get('REMOTE_ADDR'),
                        "errors": serializer.errors,
                    },
                )

                # Format errors for better frontend handling
                errors = {}
                for field, field_errors in serializer.errors.items():
                    if field == 'non_field_errors':
                        errors['general'] = field_errors[0] if field_errors else 'Validation error occurred'
                    else:
                        errors[field] = field_errors[0] if field_errors else 'Invalid value'

                return Response({
                    'error': 'Registration failed',
                    'errors': errors
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Registration endpoint failed unexpectedly")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(PublicAuthAPIView):
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        try:
            email = request.data.get('email')
            password = request.data.get('password')

            if email and password:
                # Check if user exists first
                try:
                    user_exists = CustomUser.objects.get(email=email)
                except CustomUser.DoesNotExist:
                    return Response({'error': 'No account found with this email address.'}, status=status.HTTP_401_UNAUTHORIZED)

                # Check password manually for unverified users since authenticate() requires is_active=True
                if user_exists.check_password(password):
                    # Password is correct, now check email verification
                    if not user_exists.is_email_verified:
                        return Response({
                            'error': 'Please verify your email address before logging in.',
                            'email_verified': False,
                            'warning_type': 'email_verification_required',
                            'user_email': user_exists.email,
                            'message': 'Account access is restricted until email verification is complete.',
                            'action_required': 'verify_email'
                        }, status=status.HTTP_403_FORBIDDEN)

                    # Email is verified, use standard authenticate
                    user = authenticate(username=email, password=password)
                else:
                    user = None

                if user:
                    # Check if user has 2FA enabled
                    if user.two_factor_enabled:
                        # Check if there's already an unused 2FA code for login
                        from .utils import check_unused_codes_exist
                        has_unused_code = check_unused_codes_exist(user, 'two_factor_code', 'login')

                        if has_unused_code:
                            # User already has an unused 2FA code, proceed to verification without sending new code
                            return Response({
                                'requires_2fa': True,
                                'message': 'Two-factor authentication required. Please enter the verification code sent to your email.',
                                'email': user.email,
                                'user_id': user.id,  # Temporary identifier for 2FA verification
                                'code_already_sent': True  # Indicates no new code was sent
                            }, status=status.HTTP_200_OK)
                        else:
                            # No unused code exists, send a new one
                            success, result = send_2fa_code(user, 'login', request)
                            if success:
                                return Response({
                                    'requires_2fa': True,
                                    'message': 'Two-factor authentication required. A verification code has been sent to your email.',
                                    'email': user.email,
                                    'user_id': user.id,  # Temporary identifier for 2FA verification
                                    'code_already_sent': False  # Indicates new code was sent
                                }, status=status.HTTP_200_OK)
                            else:
                                return Response({
                                    'error': result
                                }, status=status.HTTP_429_TOO_MANY_REQUESTS)
                    else:
                        # No 2FA required, proceed with normal login
                        refresh = CustomRefreshToken.for_user(user)
                        return Response({
                            'user': UserSerializer(user).data,
                            'refresh': str(refresh),
                            'access': str(refresh.access_token),
                        })
                else:
                    return Response({'error': 'Incorrect password. Please try again.'}, status=status.HTTP_401_UNAUTHORIZED)
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Login endpoint failed unexpectedly")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginVerify2FAView(PublicAuthAPIView):
    throttle_classes = [LoginVerifyThrottle]

    def post(self, request, *args, **kwargs):
        """Complete login with 2FA verification"""
        try:
            user_id = request.data.get('user_id')
            code = request.data.get('code')

            if not user_id or not code:
                return Response({'error': 'User ID and verification code are required'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({'error': 'Invalid user ID'}, status=status.HTTP_401_UNAUTHORIZED)

            # Verify 2FA code
            success, message = verify_2fa_code(user, code, 'login')

            if not success:
                return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

            # 2FA verified, complete login
            refresh = CustomRefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'message': 'Login successful'
            })

        except Exception:
            logger.exception("Login 2FA verification failed unexpectedly")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TokenRefreshAPIView(PublicAuthAPIView):
    throttle_classes = [TokenRefreshThrottle]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh') if hasattr(request.data, 'get') else None

        if not refresh_token:
            return Response({'error': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = CustomRefreshToken(refresh_token)
        except TokenError:
            logger.warning("Invalid refresh token submitted")
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        # Prevent reuse of blacklisted tokens.
        try:
            token.check_blacklist()  # type: ignore[attr-defined]
        except TokenError:
            logger.warning("Blacklisted refresh token attempted")
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
        except AttributeError:
            # Blacklist app not installed; continue best-effort.
            logger.debug("Token blacklist check skipped (app unavailable)")

        user_id = token.payload.get('user_id') if hasattr(token, 'payload') else token.get('user_id')
        if not user_id:
            logger.warning("Refresh token missing user_id claim")
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            logger.warning("Refresh token references unknown user", extra={'user_id': user_id})
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            new_refresh = token.rotate()
            logger.debug("Refresh token rotated", extra={'user_id': user_id})
        except AttributeError:
            # Rotation unavailable—fall back to minting a new token and blacklist the old one if possible.
            try:
                token.blacklist()  # type: ignore[attr-defined]
                logger.debug("Refresh token blacklisted via fallback", extra={'user_id': user_id})
            except AttributeError:
                logger.debug("Token blacklist app not installed; cannot persist blacklist state")
            except Exception:
                logger.exception("Failed to blacklist refresh token", extra={'user_id': user_id})

            new_refresh = CustomRefreshToken.for_user(user)
            logger.debug("Issued replacement refresh token", extra={'user_id': user_id})

        # Ensure minimal, up-to-date claims on the rotated token.
        if not isinstance(new_refresh, CustomRefreshToken):
            new_refresh = CustomRefreshToken(str(new_refresh))

        for extraneous in ("is_seller", "is_admin", "first_name", "last_name"):
            new_refresh.payload.pop(extraneous, None)

        new_refresh['user_id'] = user.id
        new_refresh['role'] = user.role

        return Response({
            'refresh': str(new_refresh),
            'access': str(new_refresh.access_token)
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    token = request.data.get('token')
    
    if not token:
        return Response({'error': 'Token is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    success, message = verify_email_token(token)
    
    if success:
        return Response({'message': message}, status=status.HTTP_200_OK)
    else:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification_email(request):
    email = request.data.get('email')
    
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = CustomUser.objects.get(email=email)
        
        if user.is_email_verified:
            return Response({'error': 'Email is already verified'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Invalidate old tokens
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)
        
        # Send new verification email
        email_result = send_verification_email(user, request)
        
        if isinstance(email_result, tuple):
            email_sent, message = email_result
            if email_sent:
                return Response({'message': message}, status=status.HTTP_200_OK)
            else:
                return Response({'error': message}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        else:
            # Legacy support
            if email_result:
                return Response({'message': 'Verification email sent successfully'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Failed to send verification email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except CustomUser.DoesNotExist:
        return Response({'error': 'User with this email does not exist'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([AllowAny])
def check_email_rate_limit(request):
    """Check rate limit status for email requests"""
    try:
        email = request.data.get('email')
        request_type = request.data.get('request_type', 'email_verification')
        
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Don't reveal if email exists or not for security
            return Response({
                'can_send': True,
                'time_remaining': 0
            }, status=status.HTTP_200_OK)
        
        can_send, time_remaining = get_email_rate_limit_status(user, email, request_type)
        
        return Response({
            'can_send': can_send,
            'time_remaining': time_remaining
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GoogleLoginView(PublicAuthAPIView):
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        """
        Unified Google login/register endpoint.
        Automatically creates a new user if they don't exist, otherwise logs in existing user.
        """
        logger.info(
            "Google login request received",
            extra={"payload_keys": sorted(request.data.keys())},
        )
        serializer = GoogleAuthSerializer(data=request.data)

        if serializer.is_valid():
            google_data = serializer.validated_data
            try:
                user = CustomUser.objects.get(email=google_data['email'])
                logger.info(
                    "Existing user authenticated via Google",
                    extra={"email": _mask_email(google_data['email'])},
                )

                refresh = CustomRefreshToken.for_user(user)

                response_data = {
                    'success': True,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    },
                    'user': UserSerializer(user).data,
                    'is_new_user': False,
                }

                return Response(response_data)

            except CustomUser.DoesNotExist:
                logger.info(
                    "Creating new user from Google login",
                    extra={"email": _mask_email(google_data['email'])},
                )
                try:
                    # Automatically create new user if they don't exist
                    username = google_data['email'].split('@')[0]

                    # Ensure username is unique
                    if CustomUser.objects.filter(username=username).exists():
                        import random
                        username = f"{username}{random.randint(1, 9999)}"

                    user = CustomUser.objects.create_user(
                        username=username,
                        email=google_data['email'],
                        password=None,  # No password for Google OAuth users
                        first_name=google_data.get('given_name', ''),
                        last_name=google_data.get('family_name', ''),
                        is_email_verified=True,  # Google accounts are pre-verified
                        is_active=True,
                    )
                    logger.info(
                        "New Google user created",
                        extra={"email": _mask_email(google_data['email'])},
                    )

                    refresh = CustomRefreshToken.for_user(user)

                    response_data = {
                        'success': True,
                        'tokens': {
                            'refresh': str(refresh),
                            'access': str(refresh.access_token),
                        },
                        'user': UserSerializer(user).data,
                        'is_new_user': True,
                    }

                    return Response(response_data)

                except Exception:
                    logger.exception(
                        "Error creating user for Google account",
                        extra={"email": _mask_email(google_data['email'])},
                    )
                    return Response({
                        'success': False,
                        'error': 'Failed to create user account. Please try again.'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            logger.error(
                "Google login validation error",
                extra={"errors": serializer.errors},
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': False,
            'error': 'Unable to authenticate with Google.'
        }, status=status.HTTP_400_BAD_REQUEST)


class GoogleRegisterView(PublicAuthAPIView):
    throttle_classes = [RegistrationThrottle]

    def post(self, request, *args, **kwargs):
        """Google register endpoint - exact copy from YummiAI."""
        logger.info(
            "Google register request received",
            extra={"payload_keys": sorted(request.data.keys())},
        )
        serializer = GoogleAuthSerializer(data=request.data)

        if serializer.is_valid():
            google_data = serializer.validated_data

            try:
                user = CustomUser.objects.get(email=google_data['email'])
                is_new_user = False
                logger.info(
                    "Existing user completed Google registration",
                    extra={"email": _mask_email(google_data['email'])},
                )

            except CustomUser.DoesNotExist:
                logger.info(
                    "Creating new Google account user",
                    extra={"email": _mask_email(google_data['email'])},
                )
                username = google_data['email'].split('@')[0]

                if CustomUser.objects.filter(username=username).exists():
                    import random
                    username = f"{username}{random.randint(1, 9999)}"

                user = CustomUser.objects.create_user(
                    username=username,
                    email=google_data['email'],
                    password=None,
                    first_name=google_data.get('given_name', ''),
                    last_name=google_data.get('family_name', ''),
                    is_email_verified=True,  # Google accounts are pre-verified
                )

                is_new_user = True

            refresh = CustomRefreshToken.for_user(user)

            response_data = {
                'success': True,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'user': UserSerializer(user).data,
                'is_new_user': is_new_user
            }

            return Response(response_data)
        else:
            logger.error(
                "Google registration validation error",
                extra={"errors": serializer.errors},
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': False,
            'error': 'Unable to register with Google.'
        }, status=status.HTTP_400_BAD_REQUEST)


class GoogleOAuthLegacyView(PublicAuthAPIView):
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        """Legacy Google OAuth endpoint - redirects to new endpoints."""
        try:
            logger.info(
                "Google OAuth legacy endpoint invoked",
                extra={
                    "method": request.method,
                    "payload_keys": sorted(request.data.keys()) if request.data else [],
                },
            )

            # Accept Google user data directly (YummiAI approach)
            google_data = request.data
            email = google_data.get('email')

            logger.debug(
                "Google OAuth payload",
                extra={
                    "email": _mask_email(email),
                    "platform": google_data.get('platform', 'unknown'),
                },
            )

            if not email:
                logger.warning("Google OAuth request missing email")
                return Response({'error': 'Google email is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Check if user already exists
            try:
                user = CustomUser.objects.get(email=email)
                logger.info(
                    "Existing user authenticated via legacy Google OAuth",
                    extra={"email": _mask_email(email)},
                )
                is_new_user = False
            except CustomUser.DoesNotExist:
                logger.info(
                    "Creating new user from legacy Google OAuth",
                    extra={"email": _mask_email(email)},
                )
                # Create new user from Google data
                try:
                    # Create username from email if not provided
                    username = email.split('@')[0]
                    if CustomUser.objects.filter(username=username).exists():
                        import random
                        username = f"{username}{random.randint(1, 9999)}"

                    user = CustomUser.objects.create_user(
                        username=username,
                        email=email,
                        first_name=google_data.get('given_name', ''),
                        last_name=google_data.get('family_name', ''),
                        is_email_verified=True,  # Google accounts are pre-verified
                        is_active=True,
                    )
                    logger.info(
                        "New user created via legacy Google OAuth",
                        extra={"email": _mask_email(email)},
                    )
                    is_new_user = True
                except Exception as e:
                    logger.exception(
                        "User creation failed during legacy Google OAuth",
                        extra={"email": _mask_email(email)},
                    )
                    return Response({'error': f'Failed to create user: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            # Generate JWT tokens
            refresh = CustomRefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'is_new_user': is_new_user,
                'message': 'Google authentication successful'
            }, status=status.HTTP_200_OK)

        except Exception:
            logger.exception("Legacy Google OAuth request failed unexpectedly")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_2fa(request):
    """Enable or disable 2FA for the authenticated user"""
    try:
        serializer = TwoFactorToggleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        
        enable = serializer.validated_data['enable']
        user = request.user
        
        if enable:
            # User wants to enable 2FA
            if user.two_factor_enabled:
                return Response({'error': '2FA is already enabled'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Send 2FA code to user's email
            success, result = send_2fa_code(user, 'enable_2fa', request)
            if success:
                return Response({
                    'message': 'A 6-digit verification code has been sent to your email. Please enter it to enable 2FA.',
                    'requires_verification': True
                }, status=status.HTTP_200_OK)
            else:
                return Response({'error': result}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        else:
            # User wants to disable 2FA
            if not user.two_factor_enabled:
                return Response({'error': '2FA is already disabled'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Send 2FA code to user's email for confirmation
            success, result = send_2fa_code(user, 'disable_2fa', request)
            if success:
                return Response({
                    'message': 'A 6-digit verification code has been sent to your email. Please enter it to disable 2FA.',
                    'requires_verification': True
                }, status=status.HTTP_200_OK)
            else:
                return Response({'error': result}, status=status.HTTP_429_TOO_MANY_REQUESTS)
                
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_2fa(request):
    """Verify 2FA code and complete the 2FA toggle action"""
    try:
        serializer = TwoFactorVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid data', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        code = serializer.validated_data['code']
        purpose = serializer.validated_data['purpose']
        user = request.user
        
        # Verify the 2FA code
        success, message = verify_2fa_code(user, code, purpose)
        
        if not success:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        
        # Apply the 2FA toggle based on purpose
        if purpose == 'enable_2fa':
            user.two_factor_enabled = True
            user.save()
            return Response({
                'message': '2FA has been successfully enabled for your account.',
                'two_factor_enabled': True
            }, status=status.HTTP_200_OK)
        elif purpose == 'disable_2fa':
            user.two_factor_enabled = False
            user.save()
            return Response({
                'message': '2FA has been successfully disabled for your account.',
                'two_factor_enabled': False
            }, status=status.HTTP_200_OK)
        elif purpose == 'set_password':
            # This is handled by the set_password_with_2fa endpoint
            return Response({
                'message': 'Code verified successfully. Use the set password endpoint to complete the process.',
                'code_verified': True
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid purpose'}, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_2fa_status(request):
    """Get current 2FA status for the authenticated user"""
    try:
        user = request.user
        return Response({
            'two_factor_enabled': user.two_factor_enabled,
            'email': user.email
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_password_setup(request):
    """Request to set password for OAuth-only users (requires 2FA)"""
    try:
        user = request.user
        
        # Check if user is OAuth-only
        if not user.is_oauth_only_user():
            return Response({'error': 'Password is already set for this account'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = SetPasswordRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Send 2FA code for password setup
        success, result = send_2fa_code(user, 'set_password', request)
        if success:
            return Response({
                'message': 'A 6-digit verification code has been sent to your email. Please enter it along with your new password.',
                'requires_verification': True
            }, status=status.HTTP_200_OK)
        else:
            return Response({'error': result}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_password_with_2fa(request):
    """Set password for OAuth-only users with 2FA verification"""
    try:
        user = request.user
        
        # Check if user is OAuth-only
        if not user.is_oauth_only_user():
            return Response({'error': 'Password is already set for this account'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = SetPasswordVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid data', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        code = serializer.validated_data['code']
        password = serializer.validated_data['password']
        
        # Verify the 2FA code
        success, message = verify_2fa_code(user, code, 'set_password')
        
        if not success:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        
        # Set the password
        user.set_password(password)
        user.save()
        
        return Response({
            'message': 'Password has been successfully set for your account.',
            'is_oauth_only_user': False
        }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RequestPasswordResetView(PublicAuthAPIView):
    throttle_classes = [PasswordResetRequestThrottle]

    def post(self, request, *args, **kwargs):
        """Request password reset for any user (both regular and OAuth-only users)."""
        try:
            email = request.data.get('email') if hasattr(request.data, 'get') else None

            if not email:
                return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Email format validation
            import re
            email_regex = r'^[^@]+@[^@]+\.[^@]+$'
            if not re.match(email_regex, email):
                return Response({'error': 'Please enter a valid email address'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                # Don't reveal if email exists or not for security
                return Response({
                    'message': 'If an account with this email exists, a password reset code has been sent.',
                    'email_sent': True
                }, status=status.HTTP_200_OK)

            # Send 2FA code for password reset
            success, result = send_2fa_code(user, 'reset_password', request)
            if success:
                return Response({
                    'message': 'A 6-digit password reset code has been sent to your email.',
                    'email_sent': True,
                    'user_id': user.id  # Temporary identifier for reset verification
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': result,
                    'email_sent': False
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        except Exception:
            logger.exception("Password reset request failed")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResetPasswordWith2FAView(PublicAuthAPIView):
    throttle_classes = [PasswordResetVerifyThrottle]

    def post(self, request, *args, **kwargs):
        """Reset password with 2FA verification (reuses password setup logic)."""
        try:
            user_id = request.data.get('user_id') if hasattr(request.data, 'get') else None
            code = request.data.get('code') if hasattr(request.data, 'get') else None
            password = request.data.get('password') if hasattr(request.data, 'get') else None
            confirm_password = request.data.get('confirm_password') if hasattr(request.data, 'get') else None

            if not user_id or not code or not password or not confirm_password:
                return Response({
                    'error': 'User ID, verification code, password, and confirm password are required'
                }, status=status.HTTP_400_BAD_REQUEST)

            if password != confirm_password:
                return Response({'error': 'Passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({'error': 'Invalid reset request'}, status=status.HTTP_401_UNAUTHORIZED)

            serializer = SetPasswordVerifySerializer(
                data={'code': code, 'password': password, 'password_confirm': confirm_password}
            )
            if not serializer.is_valid():
                return Response({'error': 'Invalid data', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            # Verify the 2FA code for password reset
            success, message = verify_2fa_code(user, code, 'reset_password')

            if not success:
                return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

            # Reset the password (works for both regular users and OAuth-only users)
            user.set_password(password)
            user.save()

            return Response({
                'message': 'Password has been successfully reset for your account.',
                'is_oauth_only_user': user.is_oauth_only_user()
            }, status=status.HTTP_200_OK)

        except Exception:
            logger.exception("Password reset verification failed")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class Resend2FACodeView(PublicAuthAPIView):
    throttle_classes = [TwoFactorResendThrottle]

    def post(self, request, *args, **kwargs):
        """Resend 2FA code for login verification."""
        try:
            user_id = request.data.get('user_id') if hasattr(request.data, 'get') else None
            purpose = request.data.get('purpose', 'login') if hasattr(request.data, 'get') else 'login'

            if not user_id:
                return Response({'error': 'User ID is required'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = CustomUser.objects.get(id=user_id)
            except CustomUser.DoesNotExist:
                return Response({'error': 'Invalid user'}, status=status.HTTP_401_UNAUTHORIZED)

            if not user.two_factor_enabled:
                return Response({'error': 'Two-factor authentication is not enabled'}, status=status.HTTP_400_BAD_REQUEST)

            success, result = send_2fa_code(user, purpose, request)

            if success:
                return Response({
                    'message': 'A new verification code has been sent to your email.',
                    'email': user.email
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': result
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        except Exception:
            logger.exception("Resend 2FA code failed")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChangeLanguageView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthenticatedMutationThrottle]

    def post(self, request, *args, **kwargs):
        """Change user's language preference."""
        try:
            language_code = request.data.get('language') if hasattr(request.data, 'get') else None

            if not language_code:
                return Response({'error': 'Language code is required'}, status=status.HTTP_400_BAD_REQUEST)

            valid_languages = [choice[0] for choice in CustomUser.LANGUAGE_CHOICES]
            if language_code not in valid_languages:
                return Response({
                    'error': f'Invalid language code. Available languages: {", ".join(valid_languages)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            user = request.user
            old_language = user.language
            user.language = language_code
            user.save(update_fields=['language'])

            return Response({
                'message': 'Language preference updated successfully',
                'old_language': old_language,
                'new_language': language_code,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'language': user.language,
                }
            }, status=status.HTTP_200_OK)

        except Exception:
            logger.exception("Language change failed")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UploadProfilePictureView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthenticatedMutationThrottle]

    def post(self, request, *args, **kwargs):
        """Upload user's profile picture to S3."""
        try:
            from django.conf import settings
            from utils.s3_storage import get_s3_storage, S3StorageError

            if not getattr(settings, 'USE_S3', False):
                return Response({
                    'error': 'S3 storage is not enabled'
                }, status=status.HTTP_400_BAD_REQUEST)

            image_file = request.FILES.get('profile_picture') or request.FILES.get('image')
            if not image_file:
                return Response({
                    'error': 'Profile picture file is required (use "profile_picture" or "image" field)'
                }, status=status.HTTP_400_BAD_REQUEST)

            max_size = 10 * 1024 * 1024  # 10MB (matches S3Storage validation)
            if image_file.size > max_size:
                return Response({
                    'error': f'Image file too large. Maximum size is {max_size // (1024*1024)}MB'
                }, status=status.HTTP_400_BAD_REQUEST)

            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
            if hasattr(image_file, 'content_type') and image_file.content_type not in allowed_types:
                return Response({
                    'error': f'Invalid file type. Allowed types: {", ".join(allowed_types)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                s3_storage = get_s3_storage()

                result = s3_storage.upload_profile_picture(
                    user_id=str(request.user.id),
                    image_file=image_file,
                    replace_existing=True
                )

                profile = request.user.profile
                profile.profile_picture_url = result['key']
                profile.save()

                temp_url = profile.get_profile_picture_temp_url()

                return Response({
                    'message': 'Profile picture uploaded successfully',
                    'profile_picture_url': result['key'],
                    'profile_picture_temp_url': temp_url,
                    'size': result['size'],
                    'content_type': result['content_type'],
                    'uploaded_at': result['uploaded_at']
                }, status=status.HTTP_200_OK)

            except S3StorageError as exc:
                return Response({
                    'error': f'Failed to upload profile picture: {str(exc)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception:
            logger.exception("Profile picture upload failed")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteProfilePictureView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthenticatedMutationThrottle]

    def delete(self, request, *args, **kwargs):
        """Delete user's profile picture from S3."""
        try:
            from django.conf import settings
            from utils.s3_storage import get_s3_storage, S3StorageError

            if not getattr(settings, 'USE_S3', False):
                return Response({
                    'error': 'S3 storage is not enabled'
                }, status=status.HTTP_400_BAD_REQUEST)

            profile = request.user.profile
            if not profile.profile_picture_url:
                return Response({
                    'error': 'No profile picture to delete'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                s3_storage = get_s3_storage()

                success = s3_storage.delete_file(profile.profile_picture_url)

                if success:
                    profile.profile_picture_url = None
                    profile.save()

                    return Response({
                        'message': 'Profile picture deleted successfully'
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'error': 'Failed to delete profile picture from S3'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            except S3StorageError as exc:
                return Response({
                    'error': f'Failed to delete profile picture: {str(exc)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception:
            logger.exception("Profile picture deletion failed")
            return Response({
                'error': 'Service may be unavailable. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


