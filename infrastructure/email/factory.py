"""
Email Service Factory
======================

Factory pattern for creating email service instances based on configuration.
"""

import logging
from typing import Literal

from django.conf import settings

from .interface import EmailServiceInterface
from .mock_service import MockEmailService
from .smtp_service import SMTPEmailService


logger = logging.getLogger(__name__)

EmailBackend = Literal["smtp", "mock"]


class EmailFactory:
    """
    Factory for creating email service instances.

    Usage:
        # In settings.py
        EMAIL_SERVICE_BACKEND = 'smtp'  # or 'mock' for testing

        # In your code
        email_service = EmailFactory.create()
    """

    @staticmethod
    def create(backend: EmailBackend | None = None) -> EmailServiceInterface:
        """
        Create an email service instance.

        Args:
            backend: Email backend type ('smtp' or 'mock')
                    If None, reads from settings.EMAIL_SERVICE_BACKEND

        Returns:
            EmailServiceInterface implementation

        Raises:
            ValueError: If backend type is invalid
        """
        # Use provided backend or fall back to settings
        # Default to 'smtp' in production, 'mock' in testing
        is_testing = getattr(settings, "TESTING", False)
        default_backend = "mock" if is_testing else "smtp"

        backend_type = backend or getattr(settings, "EMAIL_SERVICE_BACKEND", default_backend)

        logger.info(f"Creating email service backend: {backend_type}")

        if backend_type == "smtp":
            return SMTPEmailService()
        elif backend_type == "mock":
            return MockEmailService()
        else:
            raise ValueError(f"Invalid email backend: {backend_type}. Must be 'smtp' or 'mock'")

    @staticmethod
    def create_smtp() -> SMTPEmailService:
        """
        Create SMTP email service explicitly.

        Returns:
            SMTPEmailService instance
        """
        return SMTPEmailService()

    @staticmethod
    def create_mock() -> MockEmailService:
        """
        Create mock email service explicitly.

        Returns:
            MockEmailService instance
        """
        return MockEmailService()
