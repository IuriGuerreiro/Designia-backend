from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from payment_system.domain.services.webhook_service import WebhookService
from payment_system.models import PaymentTransaction


User = get_user_model()


class WebhookEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="password")
        # Mock Order (since we decoupled it, but WebhookService still retrieves it for validation)
        # We need to create a real order if we test the service integration, or mock the Order.objects.get call.
        # Since we use Order.objects.get, creating a dummy order is easiest if marketplace app is available in test env.
        # Assuming marketplace app is available.
        from marketplace.models import Order

        self.order = Order.objects.create(buyer=self.user, total_amount=Decimal("100.00"), status="pending_payment")

    @patch("payment_system.domain.services.webhook_service.event_bus")
    @patch("payment_system.domain.services.webhook_service.Order")
    def test_checkout_session_completed_publishes_event(self, mock_order_model, mock_event_bus):
        # Setup mocks
        mock_order_instance = MagicMock()
        mock_order_instance.buyer = self.user
        mock_order_instance.id = self.order.id
        mock_order_model.objects.get.return_value = mock_order_instance

        # Define event payload
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "payment_intent": "pi_test_123",
                    "amount_total": 10000,
                    "currency": "usd",
                    "metadata": {"user_id": str(self.user.id), "order_id": str(self.order.id)},
                    "shipping_details": {"address": {"city": "New York", "country": "US"}},
                }
            },
        }

        # Execute
        result = WebhookService.process_event(event, "127.0.0.1")

        # Verify
        self.assertTrue(result)

        # Check event published
        mock_event_bus.publish.assert_called_once()
        args, _ = mock_event_bus.publish.call_args
        event_type = args[0]
        payload = args[1]

        self.assertEqual(event_type, "payment.succeeded")
        self.assertEqual(payload["order_id"], str(self.order.id))
        self.assertEqual(payload["amount"], Decimal("100.00"))
        self.assertEqual(payload["shipping_details"]["city"], "New York")

        # Verify Order was NOT saved directly by WebhookService (mock order save not called)
        mock_order_instance.save.assert_not_called()

    @patch("payment_system.domain.services.webhook_service.event_bus")
    def test_refund_updated_publishes_event(self, mock_event_bus):
        # Create transaction/tracker
        PaymentTransaction.objects.create(
            order_id=self.order.id,  # Using ID for decoupling test
            seller=self.user,
            buyer=self.user,
            gross_amount=Decimal("10.00"),
            status="waiting_refund",
            stripe_payment_intent_id="pi_test_123",
        )

        event = {
            "type": "refund.updated",
            "data": {
                "object": {
                    "id": "re_test_123",
                    "status": "succeeded",
                    "amount": 1000,
                    "currency": "usd",
                    "metadata": {"order_id": str(self.order.id), "reason": "Customer request"},
                }
            },
        }

        result = WebhookService.process_event(event, "127.0.0.1")
        self.assertTrue(result)

        # Check event
        mock_event_bus.publish.assert_called_once()
        args, _ = mock_event_bus.publish.call_args
        self.assertEqual(args[0], "payment.refunded")
        self.assertEqual(args[1]["order_id"], str(self.order.id))
