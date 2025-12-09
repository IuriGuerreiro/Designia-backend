"""
Internal API Endpoints

HTTP API for service-to-service communication.
These endpoints are NOT exposed through Kong Gateway - internal network only.

Security:
- No authentication required (internal network trust)
- Should only be accessible within Docker network / Kubernetes cluster
- NOT exposed to public internet

Use Cases:
- Other services (marketplace, orders) fetching user data
- Fast JWT validation without DB queries
- Batch user lookups
"""

import logging

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from authentication.domain.models import CustomUser

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([])  # No auth - internal network only
def internal_get_user(request, user_id):
    """
    Internal API: Get user by ID.

    Used by other services (marketplace, orders) to fetch user data.
    Not exposed through API Gateway - internal network only.

    Args:
        user_id (UUID): User ID

    Returns:
        200: User data
        404: User not found

    Example:
        GET /internal/auth/users/123e4567-e89b-12d3-a456-426614174000/

        Response:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "email": "user@example.com",
            "username": "johndoe",
            "first_name": "John",
            "last_name": "Doe",
            "role": "seller",
            "is_email_verified": true,
            "is_active": true,
            "is_seller": true
        }
    """
    try:
        user = CustomUser.objects.get(id=user_id)
        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "is_email_verified": user.is_email_verified,
                "is_active": user.is_active,
                "is_seller": user.role == "seller",
                "two_factor_enabled": user.two_factor_enabled,
            },
            status=status.HTTP_200_OK,
        )
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as e:
        return Response({"error": f"Invalid user ID format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([])
def internal_validate_token(request):
    """
    Internal API: Validate JWT token.

    Returns user info if token is valid.
    Used by services that need fast token validation.

    Request Body:
        {
            "token": "eyJhbGc..."
        }

    Returns:
        200: Token valid
        401: Token invalid/expired

    Example:
        POST /internal/auth/validate-token/
        {
            "token": "eyJhbGc..."
        }

        Response (valid):
        {
            "valid": true,
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "email": "user@example.com",
            "role": "seller",
            "exp": 1735689600
        }

        Response (invalid):
        {
            "valid": false,
            "error": "Token is invalid or expired"
        }
    """
    token = request.data.get("token")
    if not token:
        return Response({"error": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import AccessToken

        # Validate token
        access_token = AccessToken(token)

        # Extract payload
        payload = access_token.payload

        return Response(
            {
                "valid": True,
                "user_id": str(payload.get("user_id")),
                "email": payload.get("email"),
                "role": payload.get("role"),
                "exp": payload.get("exp"),
            },
            status=status.HTTP_200_OK,
        )

    except TokenError as e:
        return Response({"valid": False, "error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return Response({"valid": False, "error": "Token validation failed"}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(["POST"])
@permission_classes([])
def internal_batch_get_users(request):
    """
    Internal API: Get multiple users by IDs (batch query).

    Used by services that need to fetch many users at once.
    More efficient than multiple single-user requests.

    Request Body:
        {
            "user_ids": ["uuid1", "uuid2", "uuid3"]
        }

    Returns:
        200: List of users (only found users)

    Example:
        POST /internal/auth/users/batch/
        {
            "user_ids": [
                "123e4567-e89b-12d3-a456-426614174000",
                "223e4567-e89b-12d3-a456-426614174001"
            ]
        }

        Response:
        {
            "users": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "user1@example.com",
                    "username": "user1",
                    "role": "customer"
                },
                {
                    "id": "223e4567-e89b-12d3-a456-426614174001",
                    "email": "user2@example.com",
                    "username": "user2",
                    "role": "seller"
                }
            ]
        }
    """
    user_ids = request.data.get("user_ids", [])

    if not user_ids:
        return Response({"users": []}, status=status.HTTP_200_OK)

    if not isinstance(user_ids, list):
        return Response({"error": "user_ids must be a list"}, status=status.HTTP_400_BAD_REQUEST)

    # Limit batch size to prevent abuse
    max_batch_size = 100
    if len(user_ids) > max_batch_size:
        return Response({"error": f"Maximum batch size is {max_batch_size}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        users = CustomUser.objects.filter(id__in=user_ids)
        return Response(
            {
                "users": [
                    {
                        "id": str(user.id),
                        "email": user.email,
                        "username": user.username,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "role": user.role,
                        "is_seller": user.role == "seller",
                    }
                    for user in users
                ]
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.error(f"Batch user fetch error: {e}")
        return Response({"error": "Failed to fetch users"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([])
def internal_check_user_email(request, email):
    """
    Internal API: Check if email exists.

    Used by other services to check email availability.
    Does NOT reveal if email exists (returns same response for security).

    Args:
        email (str): Email address to check

    Returns:
        200: Email check result

    Example:
        GET /internal/auth/check-email/user@example.com/

        Response:
        {
            "exists": true,
            "is_verified": true,
            "user_id": "123e4567-e89b-12d3-a456-426614174000"
        }
    """
    try:
        user = CustomUser.objects.get(email=email)
        return Response(
            {"exists": True, "is_verified": user.is_email_verified, "user_id": str(user.id)}, status=status.HTTP_200_OK
        )
    except CustomUser.DoesNotExist:
        return Response({"exists": False, "is_verified": False, "user_id": None}, status=status.HTTP_200_OK)
