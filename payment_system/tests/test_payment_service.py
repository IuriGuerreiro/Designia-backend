"""
Tests for PaymentService - Orchestration Layer

Stories 4.1
"""

from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from infrastructure.payments.interface import (
    CheckoutSession,
    PaymentException,
    PaymentIntent,
    PaymentProviderInterface,
    PaymentStatus,
)
from marketplace.models import Category, Order, OrderItem, Product
from marketplace.services.base import ErrorCodes
from marketplace.services.order_service import OrderService
from payment_system.services.payment_service import PaymentService

User = get_user_model()


class PaymentServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="password")
        self.seller = User.objects.create_user(username="seller", email="seller@example.com", password="password")

        self.category = Category.objects.create(name="Test Category", slug="test-category")

        self.product = Product.objects.create(
            name="Test Product", price=Decimal("100.00"), seller=self.seller, category=self.category, stock_quantity=10
        )

        # Create a pending order
        self.order = Order.objects.create(
            buyer=self.user,
            status="pending_payment",
            payment_status="pending",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            shipping_address={"street": "123 Test St"},
        )

        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=self.seller,
            quantity=1,
            unit_price=Decimal("100.00"),
            product_name="Test Product",
            product_description="Desc",
        )

        # Mock dependencies
        self.mock_provider = MagicMock(spec=PaymentProviderInterface)
        self.mock_order_service = MagicMock(spec=OrderService)

        self.service = PaymentService(payment_provider=self.mock_provider, order_service=self.mock_order_service)

    def test_initiate_payment_success(self):
        # Setup mock return
        mock_session = CheckoutSession(
            session_id="sess_123",
            url="https://checkout.stripe.com/...",
            amount=10000,
            currency="usd",
            status=PaymentStatus.PENDING,
            metadata={"order_id": str(self.order.id)},
        )
        self.mock_provider.create_checkout_session.return_value = mock_session

        # Execute
        result = self.service.initiate_payment(
            self.order, success_url="https://example.com/success", cancel_url="https://example.com/cancel"
        )

        # Assert
        self.assertTrue(result.ok)
        self.assertEqual(result.value, mock_session)

        expected_line_items = [{"name": "Test Product", "quantity": 1, "amount": Decimal("100.00"), "currency": "usd"}]

        self.mock_provider.create_checkout_session.assert_called_once_with(
            amount=self.order.total_amount,
            currency="usd",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={"order_id": str(self.order.id)},
            customer_email=self.order.buyer.email,
            line_items=expected_line_items,
        )

    def test_initiate_payment_already_paid(self):
        self.order.payment_status = "paid"

        result = self.service.initiate_payment(
            self.order, success_url="https://example.com/success", cancel_url="https://example.com/cancel"
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_ORDER_STATE)
        self.mock_provider.create_checkout_session.assert_not_called()

    def test_initiate_payment_provider_error(self):
        self.mock_provider.create_checkout_session.side_effect = PaymentException("Provider failed")

        result = self.service.initiate_payment(
            self.order, success_url="https://example.com/success", cancel_url="https://example.com/cancel"
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.PAYMENT_PROVIDER_ERROR)

    def test_confirm_payment_success(self):
        # Setup intent mock
        intent_id = "pi_123"
        mock_intent = PaymentIntent(
            intent_id=intent_id,
            amount=10000,
            currency="usd",
            status=PaymentStatus.SUCCEEDED,
            metadata={"order_id": str(self.order.id)},
        )
        self.mock_provider.retrieve_payment_intent.return_value = mock_intent

        # Setup order service mock
        self.mock_order_service.confirm_payment.return_value = MagicMock(ok=True, value=self.order)

        # Execute
        result = self.service.confirm_payment(intent_id)

        # Assert
        self.assertTrue(result.ok)
        self.mock_provider.retrieve_payment_intent.assert_called_with(intent_id)
        self.mock_order_service.confirm_payment.assert_called_with(str(self.order.id))

    def test_confirm_payment_not_succeeded(self):
        intent_id = "pi_123"
        mock_intent = PaymentIntent(
            intent_id=intent_id,
            amount=10000,
            currency="usd",
            status=PaymentStatus.FAILED,  # Failed status
            metadata={"order_id": str(self.order.id)},
        )
        self.mock_provider.retrieve_payment_intent.return_value = mock_intent

        result = self.service.confirm_payment(intent_id)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.PAYMENT_FAILED)
        self.mock_order_service.confirm_payment.assert_not_called()

    def test_confirm_payment_missing_metadata(self):
        intent_id = "pi_123"
        mock_intent = PaymentIntent(
            intent_id=intent_id,
            amount=10000,
            currency="usd",
            status=PaymentStatus.SUCCEEDED,
            metadata={},  # Missing order_id
        )
        self.mock_provider.retrieve_payment_intent.return_value = mock_intent

        result = self.service.confirm_payment(intent_id)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_PAYMENT_DATA)

    def test_refund_payment_success(self):
        # Setup order as paid
        self.order.payment_status = "paid"
        # Mock attribute injection since payment_intent_id is not on model yet
        self.order.payment_intent_id = "pi_123"

        self.mock_provider.create_refund.return_value = True

        result = self.service.refund_payment(self.order)

        self.assertTrue(result.ok)
        self.assertTrue(result.value)
        self.mock_provider.create_refund.assert_called_with(payment_intent_id="pi_123", amount=None, reason=None)
        # Verify status update (using real order obj, not mock)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "refunded")
        self.assertEqual(self.order.status, "refunded")

    def test_refund_payment_unpaid_order(self):
        # Order is pending by default
        result = self.service.refund_payment(self.order)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_ORDER_STATE)
        self.mock_provider.create_refund.assert_not_called()

    def test_get_payment_status(self):
        self.order.payment_intent_id = "pi_123"

        mock_intent = PaymentIntent(intent_id="pi_123", amount=10000, currency="usd", status=PaymentStatus.SUCCEEDED)
        self.mock_provider.retrieve_payment_intent.return_value = mock_intent

        result = self.service.get_payment_status(self.order)

        self.assertTrue(result.ok)
        self.assertEqual(result.value, PaymentStatus.SUCCEEDED)
