import logging

from django.contrib.auth import get_user_model

from .services import google_oauth as google_service

User = get_user_model()
logger = logging.getLogger(__name__)


class GoogleAuth:
    @staticmethod
    def verify_google_token(token):
        """Delegate Google token verification to service layer."""
        return google_service.verify_google_token(token)

    @staticmethod
    def get_or_create_user(google_user_info):
        """Delegate Google user get/create to service layer."""
        return google_service.get_or_create_user(google_user_info)

    @staticmethod
    def generate_tokens(user):
        """Delegate token generation to service layer."""
        return google_service.generate_tokens(user)
