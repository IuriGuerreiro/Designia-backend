"""
Service Container Tests
========================

Unit tests for dependency injection container.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from infrastructure.container import ServiceContainer, container, get_email, get_payment, get_storage
from infrastructure.email import EmailServiceInterface, MockEmailService
from infrastructure.payments import PaymentProviderInterface, StripeProvider
from infrastructure.storage import S3StorageAdapter, StorageInterface


class ServiceContainerTest(TestCase):
    """Test ServiceContainer implementation."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset container before each test
        container.reset()

    def test_container_is_singleton(self):
        """Test that ServiceContainer is a singleton."""
        container1 = ServiceContainer()
        container2 = ServiceContainer()

        self.assertIs(container1, container2)
        self.assertIs(container1, container)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_get_storage_service(self, mock_storage):
        """Test getting storage service from container."""
        mock_storage.return_value = MagicMock()

        storage = container.storage()

        self.assertIsInstance(storage, StorageInterface)
        self.assertIsInstance(storage, S3StorageAdapter)

        # Second call should return cached instance
        storage2 = container.storage()
        self.assertIs(storage, storage2)

    @override_settings(EMAIL_SERVICE_BACKEND="mock")
    def test_get_email_service(self):
        """Test getting email service from container."""
        email = container.email()

        self.assertIsInstance(email, EmailServiceInterface)
        self.assertIsInstance(email, MockEmailService)

        # Second call should return cached instance
        email2 = container.email()
        self.assertIs(email, email2)

    @override_settings(PAYMENT_PROVIDER="stripe")
    def test_get_payment_service(self):
        """Test getting payment service from container."""
        payment = container.payment()

        self.assertIsInstance(payment, PaymentProviderInterface)
        self.assertIsInstance(payment, StripeProvider)

        # Second call should return cached instance
        payment2 = container.payment()
        self.assertIs(payment, payment2)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_get_storage_returns_s3(self, mock_storage):
        """Test getting storage returns S3 adapter."""
        mock_storage.return_value = MagicMock()

        storage = container.storage()
        self.assertIsInstance(storage, S3StorageAdapter)

    def test_email_with_explicit_backend(self):
        """Test getting email with explicit backend."""
        email = container.email("mock")
        self.assertIsInstance(email, MockEmailService)

    def test_payment_with_explicit_backend(self):
        """Test getting payment with explicit backend."""
        payment = container.payment("stripe")
        self.assertIsInstance(payment, StripeProvider)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_reset_container(self, mock_storage):
        """Test resetting container clears cached instances."""
        mock_storage.return_value = MagicMock()

        # Get services
        storage1 = container.storage()
        email1 = container.email("mock")

        # Reset container
        container.reset()

        # Get services again
        storage2 = container.storage()
        email2 = container.email("mock")

        # Should be different instances
        self.assertIsNot(storage1, storage2)
        self.assertIsNot(email1, email2)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_configure_for_testing(self, mock_storage):
        """Test configuring container for testing."""
        mock_storage.return_value = MagicMock()

        container.configure_for_testing()

        storage = container.storage()
        email = container.email()
        payment = container.payment()

        self.assertIsInstance(storage, S3StorageAdapter)
        self.assertIsInstance(email, MockEmailService)
        self.assertIsInstance(payment, StripeProvider)


class ConvenienceFunctionsTest(TestCase):
    """Test convenience functions for service access."""

    def setUp(self):
        """Set up test fixtures."""
        container.reset()

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_get_storage_function(self, mock_storage):
        """Test get_storage convenience function."""
        mock_storage.return_value = MagicMock()

        storage = get_storage()

        self.assertIsInstance(storage, StorageInterface)
        self.assertIsInstance(storage, S3StorageAdapter)

    @override_settings(EMAIL_SERVICE_BACKEND="mock")
    def test_get_email_function(self):
        """Test get_email convenience function."""
        email = get_email()

        self.assertIsInstance(email, EmailServiceInterface)
        self.assertIsInstance(email, MockEmailService)

    @override_settings(PAYMENT_PROVIDER="stripe")
    def test_get_payment_function(self):
        """Test get_payment convenience function."""
        payment = get_payment()

        self.assertIsInstance(payment, PaymentProviderInterface)
        self.assertIsInstance(payment, StripeProvider)
