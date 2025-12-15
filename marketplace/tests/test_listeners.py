from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from marketplace.infra.events.listeners import (
    handle_payment_refunded,
    handle_payment_succeeded,
)
from marketplace.models import Order


User = get_user_model()


class ListenerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="listener_test", password="password")
        self.order = Order.objects.create(buyer=self.user, total_amount=Decimal("100.00"), status="pending_payment")

    @patch("marketplace.infra.events.listeners.OrderService")
    def test_handle_payment_succeeded(self, mock_service_class):
        # Setup mock service
        mock_service = mock_service_class.return_value
        mock_service.confirm_payment.return_value = MagicMock(ok=True)

        event_data = {
            "payload": {
                "order_id": str(self.order.id),
                "amount": 100.00,
                "shipping_details": {"address": "123 Test St"},
            }
        }

        handle_payment_succeeded(event_data)

        # Verify service call
        mock_service.confirm_payment.assert_called_once_with(str(self.order.id), {"address": "123 Test St"})

    @patch("marketplace.infra.events.listeners.OrderService")
    def test_handle_payment_refunded(self, mock_service_class):
        mock_service = mock_service_class.return_value
        mock_service.process_refund_success.return_value = MagicMock(ok=True)

        event_data = {"payload": {"order_id": str(self.order.id), "amount": "10.00", "reason": "defect"}}

        handle_payment_refunded(event_data)

        mock_service.process_refund_success.assert_called_once()
        args = mock_service.process_refund_success.call_args[0]
        self.assertEqual(args[0], str(self.order.id))
        self.assertEqual(args[1], Decimal("10.00"))  # Ensure decimal conversion
        self.assertEqual(args[2], "defect")
