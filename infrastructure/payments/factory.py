"""
Payment Provider Factory
=========================

Factory pattern for creating payment provider instances based on configuration.
"""

import logging
from typing import Literal

from django.conf import settings

from .interface import PaymentProviderInterface
from .stripe_provider import StripeProvider

logger = logging.getLogger(__name__)

PaymentBackend = Literal["stripe"]


class PaymentFactory:
    """
    Factory for creating payment provider instances.

    Usage:
        # In settings.py
        PAYMENT_PROVIDER = 'stripe'  # Future: 'paypal', 'square', etc.

        # In your code
        payment_provider = PaymentFactory.create()
    """

    @staticmethod
    def create(backend: PaymentBackend | None = None) -> PaymentProviderInterface:
        """
        Create a payment provider instance.

        Args:
            backend: Payment backend type ('stripe', etc.)
                    If None, reads from settings.PAYMENT_PROVIDER

        Returns:
            PaymentProviderInterface implementation

        Raises:
            ValueError: If backend type is invalid
        """
        # Use provided backend or fall back to settings
        backend_type = backend or getattr(settings, "PAYMENT_PROVIDER", "stripe")

        logger.info(f"Creating payment provider: {backend_type}")

        if backend_type == "stripe":
            return StripeProvider()
        else:
            raise ValueError(f"Invalid payment provider: {backend_type}. " f"Currently only 'stripe' is supported")

    @staticmethod
    def create_stripe() -> StripeProvider:
        """
        Create Stripe payment provider explicitly.

        Returns:
            StripeProvider instance
        """
        return StripeProvider()
