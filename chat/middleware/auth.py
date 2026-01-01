import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


logger = logging.getLogger(__name__)


class HandshakeAuthMiddleware:
    """
    Custom middleware to authenticate WebSocket connections via JWT in query params.
    Intended to be used *after* AuthMiddlewareStack (which handles sessions).
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # 1. Check if user is already authenticated via session (AuthMiddlewareStack)
        if "user" in scope and not isinstance(scope["user"], AnonymousUser):
            return await self.inner(scope, receive, send)

        # 2. Try JWT from query string
        try:
            query_string = scope.get("query_string", b"").decode()
            params = parse_qs(query_string)
            token_list = params.get("token")

            if token_list:
                token = token_list[0]
                user = await self.get_user_from_token(token)

                if user:
                    scope["user"] = user
                    logger.debug(f"Authenticated user {user.id} via WebSocket JWT")
                else:
                    logger.debug("Invalid JWT token provided in WebSocket handshake")
        except Exception as e:
            logger.error(f"Error in HandshakeAuthMiddleware: {e}")

        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            jwt_auth = JWTAuthentication()
            validated_token = jwt_auth.get_validated_token(token)
            return jwt_auth.get_user(validated_token)
        except (InvalidToken, TokenError):
            # Token is invalid or expired
            return None
        except Exception as e:
            logger.error(f"Unexpected error validating JWT: {e}")
            return None
