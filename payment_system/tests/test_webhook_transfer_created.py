import json
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from marketplace.models import Order, Product

from ..models import PaymentTracker, PaymentTransaction

User = get_user_model()


class StripeWebhookTransferCreatedTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.seller = User.objects.create_user(username="seller", password="password", email="seller@example.com")
        self.buyer = User.objects.create_user(username="buyer", password="password", email="buyer@example.com")
        self.product = Product.objects.create(
            name="Test Product",
            price=Decimal("100.00"),
            seller=self.seller,
            stock_quantity=10,
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            total_amount=Decimal("100.00"),
        )
        self.payment_transaction = PaymentTransaction.objects.create(
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            status="processing",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("95.00"),
            stripe_payment_intent_id="pi_12345",
            metadata={
                "transaction_id": str(uuid.uuid4()),
                "order_id": str(self.order.id),
                "seller_id": str(self.seller.id),
                "buyer_id": str(self.buyer.id),
            },
        )

    def _generate_mock_transfer_event(self):
        return {
            "id": "evt_12345",
            "object": "event",
            "api_version": "2020-08-27",
            "created": 1633027200,
            "data": {
                "object": {
                    "id": "tr_12345",
                    "object": "transfer",
                    "amount": 9500,
                    "amount_reversed": 0,
                    "balance_transaction": "txn_12345",
                    "created": 1633027200,
                    "currency": "usd",
                    "description": None,
                    "destination": self.seller.stripe_account_id or "acct_12345",
                    "destination_payment": "py_12345",
                    "livemode": False,
                    "metadata": {
                        "transaction_id": str(self.payment_transaction.id),
                        "order_id": str(self.order.id),
                        "seller_id": str(self.seller.id),
                        "buyer_id": str(self.buyer.id),
                    },
                    "reversed": False,
                    "source_transaction": "ch_12345",
                    "source_type": "card",
                    "transfer_group": f"ORDER{self.order.id}",
                }
            },
            "livemode": False,
            "pending_webhooks": 1,
            "request": {"id": "req_12345", "idempotency_key": None},
            "type": "transfer.created",
        }

    @patch("stripe.Webhook.construct_event")
    def test_transfer_created_webhook_success(self, mock_construct_event):
        mock_event_data = self._generate_mock_transfer_event()
        # The event object needs to be accessible via attribute, not dict key
        mock_event = type(
            "Event", (), {"type": "transfer.created", "data": {"object": mock_event_data["data"]["object"]}}
        )()
        mock_construct_event.return_value = mock_event

        response = self.client.post(
            reverse("stripe_webhook"),
            data=json.dumps(mock_event_data),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="whsec_test_signature",
        )

        self.assertEqual(response.status_code, 200)

        # Check if PaymentTracker was created
        self.assertTrue(
            PaymentTracker.objects.filter(
                stripe_transfer_id="tr_12345",
                transaction_type="transfer",
                status="succeeded",
            ).exists()
        )
        tracker = PaymentTracker.objects.get(stripe_transfer_id="tr_12345")
        self.assertEqual(tracker.order, self.order)
        self.assertEqual(tracker.user, self.seller)
        self.assertEqual(tracker.amount, Decimal("95.00"))

        # Check if PaymentTransaction was updated
        self.payment_transaction.refresh_from_db()
        self.assertEqual(self.payment_transaction.status, "completed")
        self.assertIn(
            "Transfer completed via webhook: tr_12345",
            self.payment_transaction.notes,
        )
