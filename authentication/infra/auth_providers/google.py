"""
Google Authentication Provider Implementation.
"""

import logging
import os
from typing import Any, Dict, Optional

from .base import AuthProvider


logger = logging.getLogger(__name__)


class GoogleAuthProvider(AuthProvider):
    """
    Implementation of AuthProvider for Google Sign-In.
    """

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify Google ID token.

        Requires 'google-auth' library installed.
        """
        try:
            # Import lazily to avoid hard dependency at module level
            from google.auth.transport import requests
            from google.oauth2 import id_token
        except ImportError:
            logger.error("Google auth libraries not installed (pip install google-auth)")
            return None

        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        if not client_id:
            logger.error("GOOGLE_OAUTH_CLIENT_ID environment variable not set")
            return None

        try:
            # Verify the token with Google
            id_info = id_token.verify_oauth2_token(token, requests.Request(), client_id)

            # Check issuer
            if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
                logger.warning("Invalid Google token issuer")
                return None

            return id_info

        except ValueError as e:
            # Invalid token
            logger.warning(f"Invalid Google token: {e}")
            return None
        except Exception as e:
            logger.exception(f"Google token verification failed: {e}")
            return None
