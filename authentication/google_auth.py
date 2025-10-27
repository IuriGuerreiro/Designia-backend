import os
import logging
import re
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

# Import Google auth modules only when needed to avoid import errors
logger = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def _mask_email(email: str | None) -> str | None:
    if not email:
        return None

    def _replacer(match: re.Match) -> str:
        local_part, domain = match.groups()
        if len(local_part) <= 2:
            masked_local = local_part[0] + "***"
        else:
            masked_local = f"{local_part[0]}***{local_part[-1]}"
        return f"{masked_local}@{domain}"

    return _EMAIL_PATTERN.sub(_replacer, email)


try:
    from google.auth.transport import requests
    from google.oauth2 import id_token
    GOOGLE_AUTH_AVAILABLE = True
except ImportError as e:
    GOOGLE_AUTH_AVAILABLE = False
    logger.warning(
        "Google auth libraries import failed",
        extra={"error": str(e)},
    )
    logger.warning(
        "Install google-auth and google-auth-oauthlib to enable Google OAuth support",
    )

User = get_user_model()

class GoogleAuth:
    @staticmethod
    def verify_google_token(token):
        """
        Verify Google ID token and return user information
        """
        logger.debug("Google auth availability status", extra={"available": GOOGLE_AUTH_AVAILABLE})
        if not GOOGLE_AUTH_AVAILABLE:
            return None, "Google authentication libraries not installed"

        try:
            # Get Google OAuth client ID from environment
            client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
            client_id_tail = client_id[-6:] if client_id else None
            logger.debug(
                "Google OAuth client ID configured",
                extra={"configured": bool(client_id), "client_tail": client_id_tail},
            )

            if not client_id:
                logger.error("Google OAuth client ID not configured in environment")
                return None, "Google OAuth client ID not configured"

            logger.debug("Verifying Google token")
            # Verify the token
            idinfo = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                client_id
            )
            logger.info(
                "Google token verified successfully",
                extra={
                    "issuer": idinfo.get('iss'),
                    "audience": idinfo.get('aud'),
                    "email": _mask_email(idinfo.get('email')),
                },
            )

            # Check if the token is issued by Google
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                logger.warning(
                    "Invalid Google token issuer",
                    extra={"issuer": idinfo.get('iss')},
                )
                return None, "Invalid token issuer"

            logger.debug("Token verification complete - returning user info")
            return idinfo, None

        except ValueError as e:
            logger.warning("Google token validation error", extra={"error": str(e)})
            return None, f"Invalid token: {str(e)}"
        except Exception as e:
            logger.exception("Google token verification failed", extra={"error": str(e)})
            return None, f"Token verification failed: {str(e)}"
    
    @staticmethod
    def get_or_create_user(google_user_info):
        """
        Get or create user from Google user information
        """
        email = google_user_info.get('email')
        logger.info(
            "Processing Google user info",
            extra={"email": _mask_email(email)},
        )

        if not email:
            logger.warning("Google user info missing email")
            return None, "Email not provided by Google"

        # Check if user already exists
        try:
            user = User.objects.get(email=email)
            logger.info(
                "Existing Google user found",
                extra={"email": _mask_email(email)},
            )
            # If user exists but signed up with regular registration,
            # we can link their Google account
            return user, None
        except User.DoesNotExist:
            logger.info(
                "Creating new Google user",
                extra={"email": _mask_email(email)},
            )
            # Create new user from Google info
            try:
                user = User.objects.create_user(
                    username=email,  # Use email as username
                    email=email,
                    first_name=google_user_info.get('given_name', ''),
                    last_name=google_user_info.get('family_name', ''),
                    is_email_verified=True,  # Google accounts are pre-verified
                    is_active=True,  # Google users are immediately active
                )
                logger.info(
                    "New Google user created",
                    extra={"email": _mask_email(email)},
                )
                return user, None
            except Exception as e:
                logger.exception("Google user creation failed", extra={"email": _mask_email(email)})
                return None, f"Failed to create user: {str(e)}"
    
    @staticmethod
    def generate_tokens(user):
        """
        Generate JWT tokens for the user
        """
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }