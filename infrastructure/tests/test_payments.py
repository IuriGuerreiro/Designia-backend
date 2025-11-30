"""
Payment Infrastructure Tests
==============================

Unit tests for payment provider abstraction layer.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import stripe
from django.test import TestCase, override_settings

from infrastructure.payments import (
    CheckoutSession,
    PaymentException,
    PaymentFactory,
    PaymentIntent,
    PaymentProviderInterface,
    PaymentStatus,
    StripeProvider,
    WebhookEvent,
)


class PaymentInterfaceTest(TestCase):
    """Test PaymentProviderInterface contract."""

    def test_interface_is_abstract(self):
        """PaymentProviderInterface should not be instantiable."""
        with self.assertRaises(TypeError):
            PaymentProviderInterface()


@override_settings(
    STRIPE_SECRET_KEY="sk_test_fake",
    STRIPE_WEBHOOK_SECRET="whsec_test_fake",
)
class StripeProviderTest(TestCase):
    """Test StripeProvider implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.provider = StripeProvider()

    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session_success(self, mock_create):
        """Test successful checkout session creation."""
        # Mock Stripe response
        mock_session = MagicMock()
        mock_session.id = "cs_test_123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_123"
        mock_session.payment_status = "unpaid"
        mock_create.return_value = mock_session

        # Create session
        result = self.provider.create_checkout_session(
            amount=Decimal("99.99"),
            currency="usd",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={"order_id": "123"},
        )

        self.assertIsInstance(result, CheckoutSession)
        self.assertEqual(result.session_id, "cs_test_123")
        self.assertIn("checkout.stripe.com", result.url)
        self.assertEqual(result.amount, 9999)  # In cents
        self.assertEqual(result.currency, "usd")
        self.assertEqual(result.status, PaymentStatus.PENDING)

    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session_stripe_error(self, mock_create):
        """Test checkout session creation with Stripe error."""
        mock_create.side_effect = stripe.error.StripeError("API error")

        with self.assertRaises(PaymentException):
            self.provider.create_checkout_session(
                amount=Decimal("50.00"),
                currency="usd",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

    @patch("stripe.checkout.Session.retrieve")
    def test_retrieve_session_success(self, mock_retrieve):
        """Test successful session retrieval."""
        mock_session = MagicMock()
        mock_session.id = "cs_test_123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_123"
        mock_session.amount_total = 9999
        mock_session.currency = "usd"
        mock_session.payment_status = "paid"
        mock_session.metadata = {}
        mock_retrieve.return_value = mock_session

        result = self.provider.retrieve_session("cs_test_123")

        self.assertIsInstance(result, CheckoutSession)
        self.assertEqual(result.session_id, "cs_test_123")
        self.assertEqual(result.status, PaymentStatus.SUCCEEDED)

    @patch("stripe.Webhook.construct_event")
    def test_verify_webhook_success(self, mock_construct):
        """Test successful webhook verification."""
        mock_event = {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_123"}},
            "created": 1234567890,
        }
        mock_construct.return_value = mock_event

        result = self.provider.verify_webhook(
            payload=b'{"test": "data"}',
            signature="test_signature",
        )

        self.assertIsInstance(result, WebhookEvent)
        self.assertEqual(result.event_id, "evt_test_123")
        self.assertEqual(result.event_type, "checkout.session.completed")

    @patch("stripe.Webhook.construct_event")
    def test_verify_webhook_invalid_signature(self, mock_construct):
        """Test webhook verification with invalid signature."""
        mock_construct.side_effect = stripe.error.SignatureVerificationError("Invalid signature", "sig_header")

        with self.assertRaises(PaymentException):
            self.provider.verify_webhook(
                payload=b'{"test": "data"}',
                signature="invalid_signature",
            )

    @patch("stripe.Refund.create")
    def test_create_refund_success(self, mock_create):
        """Test successful refund creation."""
        mock_refund = MagicMock()
        mock_refund.id = "re_test_123"
        mock_refund.status = "succeeded"
        mock_create.return_value = mock_refund

        result = self.provider.create_refund(
            payment_intent_id="pi_test_123",
            amount=Decimal("50.00"),
            reason="requested_by_customer",
        )

        self.assertTrue(result)
        mock_create.assert_called_once()

    @patch("stripe.PaymentIntent.retrieve")
    def test_retrieve_payment_intent_success(self, mock_retrieve):
        """Test successful payment intent retrieval."""
        mock_intent = MagicMock()
        mock_intent.id = "pi_test_123"
        mock_intent.amount = 9999
        mock_intent.currency = "usd"
        mock_intent.status = "succeeded"
        mock_intent.receipt_email = "customer@example.com"
        mock_intent.metadata = {}
        mock_retrieve.return_value = mock_intent

        result = self.provider.retrieve_payment_intent("pi_test_123")

        self.assertIsInstance(result, PaymentIntent)
        self.assertEqual(result.intent_id, "pi_test_123")
        self.assertEqual(result.status, PaymentStatus.SUCCEEDED)
        self.assertEqual(result.customer_email, "customer@example.com")

    def test_map_stripe_status(self):
        """Test Stripe status mapping."""
        # Test various status mappings
        self.assertEqual(self.provider._map_stripe_status("unpaid"), PaymentStatus.PENDING)
        self.assertEqual(self.provider._map_stripe_status("paid"), PaymentStatus.SUCCEEDED)

    def test_map_stripe_payment_status(self):
        """Test Stripe payment intent status mapping."""
        self.assertEqual(self.provider._map_stripe_payment_status("requires_payment_method"), PaymentStatus.PENDING)
        self.assertEqual(self.provider._map_stripe_payment_status("processing"), PaymentStatus.PROCESSING)
        self.assertEqual(self.provider._map_stripe_payment_status("succeeded"), PaymentStatus.SUCCEEDED)
        self.assertEqual(self.provider._map_stripe_payment_status("canceled"), PaymentStatus.CANCELED)


class PaymentFactoryTest(TestCase):
    """Test PaymentFactory."""

    @override_settings(PAYMENT_PROVIDER="stripe")
    def test_create_stripe_provider(self):
        """Test factory creates Stripe provider from settings."""
        provider = PaymentFactory.create()
        self.assertIsInstance(provider, StripeProvider)

    def test_create_with_explicit_backend(self):
        """Test factory with explicit backend."""
        provider = PaymentFactory.create("stripe")
        self.assertIsInstance(provider, StripeProvider)

    def test_create_invalid_backend(self):
        """Test factory raises error for invalid backend."""
        with self.assertRaises(ValueError):
            PaymentFactory.create("invalid")

    def test_create_stripe_explicit(self):
        """Test explicit Stripe creation."""
        provider = PaymentFactory.create_stripe()
        self.assertIsInstance(provider, StripeProvider)


class PaymentStatusTest(TestCase):
    """Test PaymentStatus enum."""

    def test_payment_status_values(self):
        """Test PaymentStatus enum has expected values."""
        self.assertEqual(PaymentStatus.PENDING.value, "pending")
        self.assertEqual(PaymentStatus.PROCESSING.value, "processing")
        self.assertEqual(PaymentStatus.SUCCEEDED.value, "succeeded")
        self.assertEqual(PaymentStatus.FAILED.value, "failed")
        self.assertEqual(PaymentStatus.CANCELED.value, "canceled")
        self.assertEqual(PaymentStatus.REFUNDED.value, "refunded")
