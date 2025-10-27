from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Attach minimal role metadata to issued access tokens."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        return token


class CustomRefreshToken(RefreshToken):
    """Refresh token that carries the user's current role only."""

    @classmethod
    def for_user(cls, user):
        """Create a refresh token with minimal custom claims."""
        token = cls()
        token['user_id'] = user.id
        token['role'] = user.role
        return token
