"""
Tests for CheckoutService

Story 4.2
"""

from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from infrastructure.payments.interface import CheckoutSession, PaymentStatus
from marketplace.models import Order
from marketplace.services.base import ErrorCodes, service_err, service_ok
from payment_system.services.checkout_service import CheckoutService
from payment_system.services.payment_service import PaymentService


User = get_user_model()


class CheckoutServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="password")
        self.order = Order.objects.create(
            buyer=self.user,
            status="pending_payment",
            payment_status="pending",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            shipping_address={},
        )

        self.mock_payment_service = MagicMock(spec=PaymentService)
        self.service = CheckoutService(payment_service=self.mock_payment_service)

    def test_create_checkout_session_success(self):
        mock_session = CheckoutSession(
            session_id="cs_123",
            url="http://checkout",
            amount=10000,
            currency="usd",
            status=PaymentStatus.PENDING,
            metadata={},
        )
        self.mock_payment_service.initiate_payment.return_value = service_ok(mock_session)

        result = self.service.create_checkout_session(self.order, "http://success", "http://cancel")

        self.assertTrue(result.ok)
        self.assertEqual(result.value, mock_session)
        self.mock_payment_service.initiate_payment.assert_called_with(self.order, "http://success", "http://cancel")

    def test_create_checkout_session_already_paid(self):
        self.order.payment_status = "paid"
        result = self.service.create_checkout_session(self.order, "s", "c")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_ORDER_STATE)
        self.mock_payment_service.initiate_payment.assert_not_called()

    def test_create_checkout_session_failure(self):
        self.mock_payment_service.initiate_payment.return_value = service_err(
            ErrorCodes.PAYMENT_PROVIDER_ERROR, "Failed"
        )

        result = self.service.create_checkout_session(self.order, "s", "c")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.PAYMENT_PROVIDER_ERROR)

    def test_get_session_success(self):
        mock_session = CheckoutSession(
            session_id="cs_123",
            url="http://checkout",
            amount=10000,
            currency="usd",
            status=PaymentStatus.PENDING,
            metadata={},
        )
        # Mock the provider chain
        self.mock_payment_service.payment_provider = MagicMock()
        self.mock_payment_service.payment_provider.retrieve_session.return_value = mock_session

        result = self.service.get_session("cs_123")

        self.assertTrue(result.ok)
        self.assertEqual(result.value, mock_session)

    def test_validate_session_valid(self):
        mock_session = CheckoutSession(
            session_id="cs_123", url="", amount=100, currency="usd", status=PaymentStatus.PENDING, metadata={}
        )
        self.service.get_session = MagicMock(return_value=service_ok(mock_session))

        result = self.service.validate_session("cs_123")
        self.assertTrue(result.ok)
        self.assertTrue(result.value)

    def test_validate_session_invalid_status(self):
        mock_session = CheckoutSession(
            session_id="cs_123", url="", amount=100, currency="usd", status=PaymentStatus.CANCELED, metadata={}
        )
        self.service.get_session = MagicMock(return_value=service_ok(mock_session))

        result = self.service.validate_session("cs_123")
        self.assertTrue(result.ok)
        self.assertFalse(result.value)
