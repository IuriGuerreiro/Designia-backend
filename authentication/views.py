from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import CustomUser, EmailVerificationToken, TwoFactorCode, EmailRequestAttempt
from .serializers import UserRegistrationSerializer, UserSerializer, GoogleAuthSerializer, TwoFactorToggleSerializer, TwoFactorVerifySerializer, SetPasswordRequestSerializer, SetPasswordVerifySerializer
from .utils import send_verification_email, verify_email_token, send_2fa_code, verify_2fa_code, get_email_rate_limit_status
from .google_auth import GoogleAuth


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
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
                    return Response({
                        'error': message,
                        'email': user.email,
                        'email_sent': False
                    }, status=status.HTTP_429_TOO_MANY_REQUESTS)
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
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
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
                    refresh = RefreshToken.for_user(user)
                    return Response({
                        'user': UserSerializer(user).data,
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    })
            else:
                return Response({'error': 'Incorrect password. Please try again.'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def login_verify_2fa(request):
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
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'message': 'Login successful'
        })
        
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def token_refresh(request):
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            refresh = RefreshToken(refresh_token)
            return Response({
                'access': str(refresh.access_token),
            })
        except Exception:
            return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
    return Response({'error': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)


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


# Google Login View (YummiAI exact copy)
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    """
    Unified Google login/register endpoint
    Automatically creates a new user if they don't exist, otherwise logs in existing user
    """
    print(f"Google login request received: {request.data}")
    serializer = GoogleAuthSerializer(data=request.data)
    
    if serializer.is_valid():
        google_data = serializer.validated_data
        try:
            user = CustomUser.objects.get(email=google_data['email'])
            print(f"Existing user found for Google login: {google_data['email']}")
            
            refresh = RefreshToken.for_user(user)
            
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
            print(f"User not found, creating new user for Google account: {google_data['email']}")
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
                print(f"New user created for Google account: {google_data['email']}")
                
                refresh = RefreshToken.for_user(user)
                
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
                
            except Exception as e:
                print(f"❌ Error creating user for Google account: {str(e)}")
                return Response({
                    'success': False,
                    'error': 'Failed to create user account. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        print(f"Google login error: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Google Register View (YummiAI exact copy)
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def google_register(request):
    """
    Google register endpoint - exact copy from YummiAI
    """
    print(f"Google register request received: {request.data}")
    serializer = GoogleAuthSerializer(data=request.data)
    
    if serializer.is_valid():
        google_data = serializer.validated_data
        
        try:
            user = CustomUser.objects.get(email=google_data['email'])
            is_new_user = False
            print(f"Existing user found for Google account: {google_data['email']}")
            
        except CustomUser.DoesNotExist:
            print(f"Creating new user for Google account: {google_data['email']}")
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
        
        refresh = RefreshToken.for_user(user)

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
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Legacy endpoint for backward compatibility
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def google_oauth(request):
    """
    Legacy Google OAuth endpoint - redirects to new endpoints
    """
    try:
        print("\n🔍 GOOGLE OAUTH LEGACY DEBUG:")
        print(f"Request method: {request.method}")
        print(f"Request data keys: {list(request.data.keys()) if request.data else 'No data'}")
        
        # Accept Google user data directly (YummiAI approach)
        google_data = request.data
        email = google_data.get('email')
        
        print(f"Email received: {email}")
        print(f"Platform: {google_data.get('platform', 'unknown')}")
        
        if not email:
            print("❌ No email provided")
            return Response({'error': 'Google email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        print("🔍 Getting or creating user...")
        
        # Check if user already exists
        try:
            user = CustomUser.objects.get(email=email)
            print(f"✅ Existing user found: {email}")
            is_new_user = False
        except CustomUser.DoesNotExist:
            print(f"🔍 Creating new user: {email}")
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
                print(f"✅ New user created: {email}")
                is_new_user = True
            except Exception as e:
                print(f"❌ User creation failed: {str(e)}")
                return Response({'error': f'Failed to create user: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        
        print("🔍 Generating JWT tokens...")
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        print("✅ JWT tokens generated successfully")
        
        print("✅ Google OAuth successful - returning response")
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'is_new_user': is_new_user,
            'message': 'Google authentication successful'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"❌ Google OAuth exception: {str(e)}")
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


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_reset(request):
    """Request password reset for any user (both regular and OAuth-only users)"""
    try:
        email = request.data.get('email')
        
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Email format validation
        import re
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
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
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_with_2fa(request):
    """Reset password with 2FA verification (reuses password setup logic)"""
    try:
        user_id = request.data.get('user_id')
        code = request.data.get('code')
        password = request.data.get('password')
        confirm_password = request.data.get('confirm_password')
        
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
        
        # Use the same password validation as SetPasswordVerifySerializer
        # Note: SetPasswordVerifySerializer expects 'password_confirm', not 'confirm_password'
        serializer = SetPasswordVerifySerializer(data={'code': code, 'password': password, 'password_confirm': confirm_password})
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
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def resend_2fa_code(request):
    """Resend 2FA code for login verification"""
    try:
        user_id = request.data.get('user_id')
        purpose = request.data.get('purpose', 'login')
        
        if not user_id:
            return Response({'error': 'User ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response({'error': 'Invalid user'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Verify that 2FA is enabled for this user
        if not user.two_factor_enabled:
            return Response({'error': 'Two-factor authentication is not enabled'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Send 2FA code (this will handle rate limiting and invalidate old codes)
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
            
    except Exception as e:
        return Response({
            'error': 'Service may be unavailable. Please try again later.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
