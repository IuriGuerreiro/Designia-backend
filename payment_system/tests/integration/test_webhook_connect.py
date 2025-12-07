import json
from unittest.mock import MagicMock, patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from marketplace.tests.factories import SellerFactory
from payment_system.models import Payout

User = get_user_model()


@override_settings(STRIPE_WEBHOOK_CONNECT_SECRET="whsec_connect_test_secret")
class StripeConnectWebhookTest(TestCase):
    def setUp(self):
        self.seller = SellerFactory(
            username="connect_seller", email="connect@example.com", stripe_account_id="acct_connect123"
        )
        self.payout = Payout.objects.create(
            stripe_payout_id="po_test_123", seller=self.seller, amount_cents=10000, currency="USD", status="pending"
        )

    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.update_payout_from_webhook")
    def test_connect_webhook_payout_paid(self, mock_update_payout, mock_construct_event):
        """Test payout.paid event processing."""
        event_data = {
            "id": "evt_payout_paid",
            "type": "payout.paid",
            "data": {
                "object": {
                    "id": "po_test_123",
                    "status": "paid",
                    "amount": 10000,
                    "currency": "usd",
                    "arrival_date": 1234567890,
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            data=MagicMock(
                object=MagicMock(
                    id="po_test_123", status="paid", amount=10000, currency="usd", arrival_date=1234567890
                )
            ),
        )
        mock_update_payout.return_value = self.payout

        response = self.client.post(
            reverse("payment_system:stripe_webhook_connect"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_update_payout.assert_called_once()

    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.update_payout_from_webhook")
    def test_connect_webhook_payout_failed(self, mock_update_payout, mock_construct_event):
        """Test payout.failed event processing."""
        event_data = {
            "id": "evt_payout_failed",
            "type": "payout.failed",
            "data": {
                "object": {
                    "id": "po_test_123",
                    "status": "failed",
                    "failure_code": "account_closed",
                    "failure_message": "The account has been closed.",
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            data=MagicMock(
                object=MagicMock(
                    id="po_test_123",
                    status="failed",
                    failure_code="account_closed",
                    failure_message="The account has been closed.",
                )
            ),
        )
        mock_update_payout.return_value = self.payout

        response = self.client.post(
            reverse("payment_system:stripe_webhook_connect"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_update_payout.assert_called_once()

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_unhandled_event(self, mock_construct_event):
        """Test unhandled event type."""
        event_data = {"id": "evt_unhandled", "type": "unhandled.event", "data": {"object": {}}}
        mock_construct_event.return_value = MagicMock(id=event_data["id"], type=event_data["type"])

        response = self.client.post(
            reverse("payment_system:stripe_webhook_connect"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_signature_error(self, mock_construct_event):
        """Test signature verification error."""
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig", "payload"
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook_connect"),
            json.dumps({}).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="invalid_signature",
        )

        self.assertEqual(response.status_code, 400)

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_parsing_error(self, mock_construct_event):
        """Test payload parsing error."""
        mock_construct_event.side_effect = Exception("Parsing failed")

        response = self.client.post(
            reverse("payment_system:stripe_webhook_connect"),
            b"invalid_json",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 400)

    def test_connect_webhook_json_error(self):
        """Test JSON decode error when constructing event from JSON directly (if secret missing or fallback)."""
        # Assuming view handles JSONDecodeError or ValueError during stripe.Event.construct_from
        # But the view catches ValueError inside `stripe.Event.construct_from` block
        with override_settings(STRIPE_WEBHOOK_CONNECT_SECRET=None):
            response = self.client.post(
                reverse("payment_system:stripe_webhook_connect"), b"invalid_json", content_type="application/json"
            )
            self.assertEqual(response.status_code, 400)
