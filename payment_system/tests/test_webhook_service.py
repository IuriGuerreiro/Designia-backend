"""
Tests for WebhookService

Story 4.3
"""

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from infrastructure.payments.interface import PaymentProviderInterface, WebhookEvent
from marketplace.models import Order
from marketplace.services.base import ErrorCodes, service_ok
from marketplace.services.order_service import OrderService
from payment_system.services.webhook_service import WebhookService

User = get_user_model()


class WebhookServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="buyer", email="buyer@example.com", password="password")
        self.order = Order.objects.create(
            buyer=self.user,
            status="pending_payment",
            payment_status="pending",
            subtotal=100,
            total_amount=100,
            shipping_address={},
        )

        self.mock_provider = MagicMock(spec=PaymentProviderInterface)
        self.mock_order_service = MagicMock(spec=OrderService)

        self.service = WebhookService(payment_provider=self.mock_provider, order_service=self.mock_order_service)

    def test_process_webhook_signature_error(self):
        self.mock_provider.verify_webhook.side_effect = Exception("Invalid signature")

        result = self.service.process_webhook(b"payload", "sig")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.PERMISSION_DENIED)

    def test_handle_checkout_completed_success(self):
        event = WebhookEvent(
            event_id="evt_123",
            event_type="checkout.session.completed",
            data={
                "object": {"id": "cs_123", "metadata": {"order_id": str(self.order.id)}, "payment_intent": "pi_123"}
            },
            created_at=1234567890,
        )
        self.mock_provider.verify_webhook.return_value = event
        self.mock_order_service.confirm_payment.return_value = service_ok(self.order)

        result = self.service.process_webhook(b"payload", "sig")

        self.assertTrue(result.ok)
        self.mock_order_service.confirm_payment.assert_called_with(str(self.order.id))

    def test_handle_payment_failed_success(self):
        event = WebhookEvent(
            event_id="evt_fail",
            event_type="payment_intent.payment_failed",
            data={
                "object": {
                    "id": "pi_fail",
                    "metadata": {"order_id": str(self.order.id)},
                    "last_payment_error": {"message": "Card declined"},
                }
            },
            created_at=1234567890,
        )
        self.mock_provider.verify_webhook.return_value = event
        self.mock_order_service.cancel_order.return_value = service_ok(True)

        result = self.service.process_webhook(b"payload", "sig")

        self.assertTrue(result.ok)
        self.mock_order_service.cancel_order.assert_called_with(
            str(self.order.id), self.order.buyer, reason="Payment failed: Card declined"
        )

    def test_handle_refund_success(self):
        event = WebhookEvent(
            event_id="evt_refund",
            event_type="charge.refunded",
            data={"object": {"id": "ch_123", "metadata": {"order_id": str(self.order.id)}, "refunded": True}},
            created_at=1234567890,
        )
        self.mock_provider.verify_webhook.return_value = event

        # Test manual update logic in handle_refund
        # We need to fetch order fresh from DB since service updates it

        result = self.service.process_webhook(b"payload", "sig")

        self.assertTrue(result.ok)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "refunded")
        self.assertEqual(self.order.status, "refunded")

    def test_ignore_unknown_event(self):
        event = WebhookEvent(event_id="evt_unknown", event_type="unknown.event", data={}, created_at=123)
        self.mock_provider.verify_webhook.return_value = event

        result = self.service.process_webhook(b"payload", "sig")

        self.assertTrue(result.ok)
        self.mock_order_service.confirm_payment.assert_not_called()
