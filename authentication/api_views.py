from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .jwt_serializers import CustomRefreshToken
from .models import CustomUser
from .serializers import UserSerializer
from .utils import send_2fa_code


class LoginAPIView(APIView):
    """
    Refactored, class-based login view.
    - Removes @csrf_exempt by using DRF's standard view handling.
    - Ready for throttling to be applied.
    """

    permission_classes = [AllowAny]
    # throttle_classes = [UserRateThrottle, AnonRateThrottle] # Throttling will be added next

    def post(self, request, *args, **kwargs):
        try:
            email = request.data.get("email")
            password = request.data.get("password")

            if not email or not password:
                return Response({"error": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                return Response(
                    {"error": "No account found with this email address."}, status=status.HTTP_401_UNAUTHORIZED
                )

            # Authenticate user
            user = authenticate(username=email, password=password)

            if user:
                if not user.is_email_verified:
                    return Response(
                        {
                            "error": "Please verify your email address before logging in.",
                            "email_verified": False,
                            "warning_type": "email_verification_required",
                            "user_email": user.email,
                            "message": "Account access is restricted until email verification is complete.",
                            "action_required": "verify_email",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if user.two_factor_enabled:
                    from .utils import check_unused_codes_exist

                    has_unused_code = check_unused_codes_exist(user, "two_factor_code", "login")

                    if has_unused_code:
                        return Response(
                            {
                                "requires_2fa": True,
                                "message": "Two-factor authentication required. Please enter the verification code sent to your email.",
                                "email": user.email,
                                "user_id": user.id,
                                "code_already_sent": True,
                            },
                            status=status.HTTP_200_OK,
                        )

                    success, result = send_2fa_code(user, "login", request)
                    if success:
                        return Response(
                            {
                                "requires_2fa": True,
                                "message": "A verification code has been sent to your email.",
                                "email": user.email,
                                "user_id": user.id,
                                "code_already_sent": False,
                            },
                            status=status.HTTP_200_OK,
                        )
                    else:
                        return Response({"error": result}, status=status.HTTP_429_TOO_MANY_REQUESTS)

                # No 2FA, log in directly
                refresh = CustomRefreshToken.for_user(user)
                return Response(
                    {
                        "user": UserSerializer(user).data,
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    }
                )
            else:
                return Response(
                    {"error": "Incorrect password. Please try again."}, status=status.HTTP_401_UNAUTHORIZED
                )

        except Exception:
            # General error handler
            return Response(
                {"error": "An unexpected error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
