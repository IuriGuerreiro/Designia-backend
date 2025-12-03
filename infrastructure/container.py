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

            # Domain Services
            self._inventory_service = None
            self._pricing_service = None
            self._cart_service = None
            self._review_service = None
            self._search_service = None
            self._order_service = None  # Added order_service

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

    def inventory_service(self):
        """Get InventoryService instance."""
        if self._inventory_service is None:
            from marketplace.services import InventoryService

            self._inventory_service = InventoryService()
            logger.debug("Created InventoryService")
        return self._inventory_service

    def pricing_service(self):
        """Get PricingService instance."""
        if self._pricing_service is None:
            from marketplace.services import PricingService

            self._pricing_service = PricingService()
            logger.debug("Created PricingService")
        return self._pricing_service

    def cart_service(self):
        """Get CartService instance."""
        if self._cart_service is None:
            from marketplace.services import CartService

            # CartService depends on InventoryService and PricingService
            self._cart_service = CartService(
                inventory_service=self.inventory_service(), pricing_service=self.pricing_service()
            )
            logger.debug("Created CartService")
        return self._cart_service

    def review_metrics_service(self):
        from marketplace.services import ReviewMetricsService

        return ReviewMetricsService()

    def review_service(self):
        """Get ReviewService instance."""
        if self._review_service is None:
            from marketplace.services import ReviewService

            self._review_service = ReviewService(review_metrics_service=self.review_metrics_service())
            logger.debug("Created ReviewService")
        return self._review_service

    def search_service(self):
        """Get SearchService instance."""
        if self._search_service is None:
            from marketplace.services import SearchService

            self._search_service = SearchService()
            logger.debug("Created SearchService")
        return self._search_service

    def order_service(self):
        """Get OrderService instance."""
        if self._order_service is None:
            from marketplace.services import OrderService

            self._order_service = OrderService(
                cart_service=self.cart_service(),
                inventory_service=self.inventory_service(),
                pricing_service=self.pricing_service(),
            )
            logger.debug("Created OrderService")
        return self._order_service

    def reset(self):
        """
        Reset all cached service instances.

        Useful for testing or when switching between environments.
        """
        self._storage = None
        self._email = None
        self._payment = None
        self._inventory_service = None
        self._pricing_service = None
        self._cart_service = None
        self._review_service = None
        self._search_service = None
        self._order_service = None  # Added reset
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


def get_payment_provider() -> PaymentProviderInterface:
    """Get payment provider (alias for get_payment)."""
    return container.payment()


# For class-based usage (static access pattern)
class Container:
    """Static access to container services."""

    @staticmethod
    def get_payment_provider() -> PaymentProviderInterface:
        return get_payment_provider()
