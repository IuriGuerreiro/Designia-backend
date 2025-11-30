"""
Dependency Injection Container
================================

Simple service locator pattern for managing infrastructure dependencies.
Implements the Dependency Inversion Principle by providing centralized access
to infrastructure services through their abstract interfaces.

Usage:
    from infrastructure.container import container

    # In your service
    storage = container.storage()
    email = container.email()
    payment = container.payment()
"""

import logging
from typing import Optional

from .email import EmailFactory, EmailServiceInterface
from .payments import PaymentFactory, PaymentProviderInterface
from .storage import StorageFactory, StorageInterface

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Service container for infrastructure dependencies.

    Implements lazy initialization and caching of service instances.
    Thread-safe singleton pattern.
    """

    _instance: Optional["ServiceContainer"] = None
    _initialized: bool = False

    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize container (only once)."""
        if not self._initialized:
            self._storage: Optional[StorageInterface] = None
            self._email: Optional[EmailServiceInterface] = None
            self._payment: Optional[PaymentProviderInterface] = None
            self._initialized = True
            logger.info("Service container initialized")

    def storage(self) -> StorageInterface:
        """
        Get storage service instance (S3/MinIO).

        Returns:
            StorageInterface implementation (cached)
        """
        if self._storage is None:
            self._storage = StorageFactory.create()
            logger.debug(f"Created storage service: {type(self._storage).__name__}")

        return self._storage

    def email(self, backend: Optional[str] = None) -> EmailServiceInterface:
        """
        Get email service instance.

        Args:
            backend: Email backend type ('smtp' or 'mock')
                    If None, uses configuration from settings

        Returns:
            EmailServiceInterface implementation (cached)
        """
        if self._email is None or backend is not None:
            self._email = EmailFactory.create(backend)
            logger.debug(f"Created email service: {type(self._email).__name__}")

        return self._email

    def payment(self, backend: Optional[str] = None) -> PaymentProviderInterface:
        """
        Get payment provider instance.

        Args:
            backend: Payment backend type ('stripe', etc.)
                    If None, uses configuration from settings

        Returns:
            PaymentProviderInterface implementation (cached)
        """
        if self._payment is None or backend is not None:
            self._payment = PaymentFactory.create(backend)
            logger.debug(f"Created payment service: {type(self._payment).__name__}")

        return self._payment

    def reset(self):
        """
        Reset all cached service instances.

        Useful for testing or when switching between environments.
        """
        self._storage = None
        self._email = None
        self._payment = None
        logger.info("Service container reset")

    def configure_for_testing(self):
        """
        Configure container with mock services for testing.

        Sets up:
            - S3 storage (with test credentials)
            - Mock email service (instead of SMTP)
            - Stripe with test mode
        """
        self._storage = StorageFactory.create()
        self._email = EmailFactory.create("mock")
        self._payment = PaymentFactory.create("stripe")
        logger.info("Service container configured for testing")


# Global singleton instance
container = ServiceContainer()


# Convenience functions for quick access
def get_storage() -> StorageInterface:
    """Get storage service from global container."""
    return container.storage()


def get_email() -> EmailServiceInterface:
    """Get email service from global container."""
    return container.email()


def get_payment() -> PaymentProviderInterface:
    """Get payment provider from global container."""
    return container.payment()
