import logging
import os
from typing import Any, Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)
User = get_user_model()


def _google_libs_available() -> bool:
    try:
        # Imported lazily to avoid hard dependency at import time
        from google.auth.transport import requests  # noqa: F401
        from google.oauth2 import id_token  # noqa: F401

        return True
    except Exception:
        return False


def verify_google_token(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Verify Google ID token and return user info or error string.

    Does not log secrets or raw tokens.
    """
    if not _google_libs_available():
        return None, "Google authentication libraries not installed"

    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token

        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        if not client_id:
            logger.error("Google OAuth client ID not configured")
            return None, "Google OAuth client ID not configured"

        idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)
        if idinfo.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
            return None, "Invalid token issuer"
        return idinfo, None
    except ValueError as e:
        logger.warning("Google token validation error")
        return None, f"Invalid token: {str(e)}"
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Google token verification failed")
        return None, f"Token verification failed: {str(e)}"


def get_or_create_user(google_user_info: Dict[str, Any]) -> Tuple[Optional[User], Optional[str]]:
    """Return an existing user or create a new one from Google profile."""
    email = google_user_info.get("email")
    if not email:
        logger.error("Google profile without email")
        return None, "Email not provided by Google"

    try:
        user = User.objects.get(email=email)
        logger.info("Google sign-in linked to existing user")
        return user, None
    except User.DoesNotExist:
        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=google_user_info.get("given_name", ""),
                last_name=google_user_info.get("family_name", ""),
                is_email_verified=True,
                is_active=True,
            )
            logger.info("Created user from Google profile")
            return user, None
        except Exception as e:  # pragma: no cover - DB/validation edge
            logger.error("Failed to create user from Google profile: %s", str(e))
            return None, f"Failed to create user: {str(e)}"


def generate_tokens(user: User) -> Dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
