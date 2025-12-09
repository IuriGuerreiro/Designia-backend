from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that includes user role in token"""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token["role"] = user.role
        token["is_seller"] = user.role == "seller"
        token["is_admin"] = user.role == "admin" or user.is_superuser
        token["first_name"] = user.first_name
        token["last_name"] = user.last_name

        return token


class CustomRefreshToken(RefreshToken):
    """Custom refresh token that includes user role"""

    @classmethod
    def for_user(cls, user):
        """Create refresh token with custom claims"""
        token = cls()
        token["user_id"] = str(user.id)
        token["role"] = user.role
        token["is_seller"] = user.role == "seller"
        token["is_admin"] = user.role == "admin" or user.is_superuser
        token["first_name"] = user.first_name
        token["last_name"] = user.last_name

        return token
