import json
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from marketplace.tests.factories import OrderFactory, OrderItemFactory, ProductFactory, SellerFactory, UserFactory
from payment_system.models import PaymentTracker, PaymentTransaction, Payout, PayoutItem


User = get_user_model()


class StripeObject:
    def __init__(self, **entries):
        self.__dict__.update(entries)
        for k, v in entries.items():
            if isinstance(v, dict):
                self.__dict__[k] = StripeObject(**v)
            if isinstance(v, list):
                self.__dict__[k] = [StripeObject(**i) if isinstance(i, dict) else i for i in v]

    def get(self, key, default=None):
        val = self.__dict__.get(key, default)
        return val

    def __getitem__(self, key):
        return self.__dict__[key]

    def keys(self):
        return self.__dict__.keys()


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
class StripeWebhookComprehensiveTest(TestCase):
    def setUp(self):
        self.buyer = UserFactory(username="buyer")
        self.seller = SellerFactory(username="seller", stripe_account_id="acct_seller123")
        self.product = ProductFactory(seller=self.seller, price=Decimal("100.00"))
        self.order = OrderFactory(
            buyer=self.buyer, status="pending_payment", payment_status="pending", total_amount=Decimal("100.00")
        )
        self.order_item = OrderItemFactory(order=self.order, product=self.product, quantity=1)

    def _to_object(self, data):
        return StripeObject(**data)

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_checkout_session_completed_success(self, mock_construct_event):
        session_id = "cs_test_complete"
        payment_intent_id = "pi_test_complete"

        event_data = {
            "id": "evt_checkout_completed",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "payment_intent": payment_intent_id,
                    "metadata": {"order_id": str(self.order.id), "user_id": str(self.buyer.id)},
                    "shipping_details": {
                        "name": "Buyer Name",
                        "address": {"line1": "123 St", "city": "City", "country": "US", "postal_code": "12345"},
                    },
                    "amount_total": 10000,
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_checkout_completed",
            type="checkout.session.completed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.shipping_address["line1"], "123 St")
        self.assertTrue(
            PaymentTracker.objects.filter(stripe_payment_intent_id=payment_intent_id, status="succeeded").exists()
        )
        self.assertTrue(
            PaymentTransaction.objects.filter(stripe_payment_intent_id=payment_intent_id, status="held").exists()
        )

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_checkout_session_completed_missing_metadata(self, mock_construct_event):
        event_data = {
            "id": "evt_checkout_missing_meta",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_missing_meta",
                    "metadata": {},  # Missing user_id/order_id
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_checkout_missing_meta",
            type="checkout.session.completed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        # Patch Session.retrieve to also return empty metadata to force failure
        with patch("payment_system.views.stripe.checkout.Session.retrieve") as mock_retrieve:
            mock_retrieve.return_value = MagicMock(metadata={})
            response = self.client.post(
                reverse("payment_system:stripe_webhook"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )
            self.assertEqual(response.status_code, 400)

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_payment_intent_succeeded(self, mock_construct_event):
        # Create tracker first to simulate checkout flow
        PaymentTracker.objects.create(
            stripe_payment_intent_id="pi_succeeded",
            order=self.order,
            user=self.buyer,
            status="pending",
            amount=Decimal("100.00"),
            currency="USD",
        )

        event_data = {
            "id": "evt_pi_succeeded",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_succeeded",
                    "amount": 10000,
                    "currency": "usd",
                    "status": "succeeded",
                    "metadata": {"order_id": str(self.order.id)},  # Add metadata
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_pi_succeeded",
            type="payment_intent.succeeded",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(self.order.status, "payment_confirmed")

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_payment_intent_failed(self, mock_construct_event):
        # Create tracker first
        PaymentTracker.objects.create(
            stripe_payment_intent_id="pi_failed",
            order=self.order,
            user=self.buyer,
            status="pending",
            amount=Decimal("100.00"),
            currency="USD",
        )

        event_data = {
            "id": "evt_pi_failed",
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_failed",
                    "amount": 10000,
                    "currency": "usd",
                    "status": "failed",
                    "last_payment_error": {"message": "Fail"},
                    "metadata": {"order_id": str(self.order.id)},  # Add metadata
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_pi_failed",
            type="payment_intent.payment_failed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed")

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_refund_updated_success(self, mock_construct_event):
        self.order.status = "payment_confirmed"
        self.order.payment_status = "paid"
        self.order.save()

        # Create waiting refund transaction
        PaymentTransaction.objects.create(
            stripe_payment_intent_id="pi_refund",
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            status="waiting_refund",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("90.00"),
            platform_fee=Decimal("10.00"),
        )

        event_data = {
            "id": "evt_refund_updated",
            "type": "refund.updated",
            "data": {
                "object": {
                    "id": "re_123",
                    "status": "succeeded",
                    "amount": 10000,
                    "metadata": {"order_id": str(self.order.id), "reason": "test"},
                    "failure_balance_transaction": None,
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_refund_updated",
            type="refund.updated",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        with patch("payment_system.views.send_order_cancellation_receipt_email", return_value=(True, "OK")):
            response = self.client.post(
                reverse("payment_system:stripe_webhook"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )
        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "refunded")

        self.assertTrue(PaymentTransaction.objects.filter(order=self.order, status="refunded").exists())
        self.assertTrue(PaymentTracker.objects.filter(stripe_refund_id="re_123", status="success_refund").exists())

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_refund_failed(self, mock_construct_event):
        self.order.status = "refunded"  # Assuming initiated
        self.order.payment_status = "paid"  # Ensure initial status is not 'failed_refund'
        self.order.save()

        PaymentTransaction.objects.create(
            stripe_payment_intent_id="pi_refund_fail",
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            status="waiting_refund",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("90.00"),
            platform_fee=Decimal("10.00"),
        )

        event_data = {
            "id": "evt_refund_failed",
            "type": "refund.failed",
            "data": {
                "object": {
                    "id": "re_fail_123",
                    "status": "failed",
                    "amount": 10000,
                    "metadata": {"order_id": str(self.order.id)},
                    "failure_reason": "expired_card",
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_refund_failed",
            type="refund.failed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        with patch("payment_system.views.send_failed_refund_notification_email", return_value=(True, "OK")):
            response = self.client.post(
                reverse("payment_system:stripe_webhook"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )
        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed_refund")
        self.assertTrue(PaymentTransaction.objects.filter(order=self.order, status="failed_refund").exists())

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_transfer_created(self, mock_construct_event):
        # Transaction in processing state
        tx = PaymentTransaction.objects.create(
            stripe_payment_intent_id="pi_transfer",
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            status="processing",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("90.00"),
            platform_fee=Decimal("10.00"),
            transfer_id="tr_temp",
        )

        event_data = {
            "id": "evt_transfer",
            "type": "transfer.created",
            "data": {
                "object": {
                    "id": "tr_real_123",
                    "amount": 9000,
                    "currency": "usd",
                    "destination": self.seller.stripe_account_id,
                    "metadata": {
                        "transaction_id": str(tx.id),
                        "order_id": str(self.order.id),
                        "seller_id": str(self.seller.id),
                        "buyer_id": str(self.buyer.id),
                    },
                    "reversed": False,
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_transfer",
            type="transfer.created",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        self.assertEqual(response.status_code, 200)

        tx.refresh_from_db()
        self.assertEqual(tx.status, "released")
        self.assertEqual(tx.transfer_id, "tr_real_123")
        self.assertTrue(PaymentTracker.objects.filter(stripe_transfer_id="tr_real_123", status="succeeded").exists())

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_transfer_created_reversed(self, mock_construct_event):
        # Transaction in processing state
        tx = PaymentTransaction.objects.create(
            stripe_payment_intent_id="pi_transfer_rev",
            order=self.order,
            seller=self.seller,
            buyer=self.buyer,
            status="processing",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("90.00"),
            platform_fee=Decimal("10.00"),
        )

        event_data = {
            "id": "evt_transfer_rev",
            "type": "transfer.created",
            "data": {
                "object": {
                    "id": "tr_rev_123",
                    "amount": 9000,
                    "currency": "usd",
                    "destination": self.seller.stripe_account_id,
                    "metadata": {"transaction_id": str(tx.id)},
                    "reversed": True,  # Reversed
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_transfer_rev",
            type="transfer.created",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        self.assertEqual(response.status_code, 200)

        tx.refresh_from_db()
        self.assertEqual(tx.status, "processing")  # Should not change status if reversed

    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.stripe_service.StripeConnectService.handle_account_updated_webhook")
    def test_webhook_account_updated(self, mock_service, mock_construct_event):
        event_data = {
            "id": "evt_acct",
            "type": "account.updated",
            "data": {"object": {"id": self.seller.stripe_account_id}},
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_acct", type="account.updated", data=MagicMock(object=self._to_object(event_data["data"]["object"]))
        )
        mock_service.return_value = {"success": True}

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        self.assertEqual(response.status_code, 200)
        mock_service.assert_called_once()

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_payout_created_fallback(self, mock_construct_event):
        """Test payout creation from webhook when not existing in DB."""
        payout_id = "po_new_payout"
        event_data = {
            "id": "evt_payout_paid",
            "type": "payout.paid",
            "data": {
                "object": {
                    "id": payout_id,
                    "status": "paid",
                    "amount": 5000,
                    "currency": "usd",
                    "arrival_date": 1234567890,
                    "metadata": {"seller_id": str(self.seller.id)},
                }
            },
        }

        # Mock event from Stripe
        mock_construct_event.return_value = MagicMock(
            id="evt_payout_paid",
            type="payout.paid",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        # We need to bypass signature verification for Connect webhook endpoint
        # But overriding STRIPE_WEBHOOK_CONNECT_SECRET in setup is needed if using that endpoint
        # Here we use standard webhook endpoint for testing logic, or ensure we use connect endpoint
        # The logic in views.py handles payout events in `stripe_webhook` OR `stripe_webhook_connect`?
        # Checking views.py: `stripe_webhook` handles `account.updated` and `transfer.created`.
        # `stripe_webhook_connect` handles `payout.*`.
        # So we must use `stripe_webhook_connect` url.

        with override_settings(STRIPE_WEBHOOK_CONNECT_SECRET="whsec_connect"):
            response = self.client.post(
                reverse("payment_system:stripe_webhook_connect"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )

        self.assertEqual(response.status_code, 200)

        # Check Payout created
        self.assertTrue(Payout.objects.filter(stripe_payout_id=payout_id).exists())
        payout = Payout.objects.get(stripe_payout_id=payout_id)
        self.assertEqual(payout.status, "paid")
        self.assertEqual(payout.seller, self.seller)

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_payout_updated_success(self, mock_construct_event):
        """Test payout update to paid status."""
        payout = Payout.objects.create(
            stripe_payout_id="po_existing", seller=self.seller, amount_cents=5000, currency="USD", status="pending"
        )

        # Transaction related to this payout
        tx = PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=self.order,
            status="released",
            gross_amount=Decimal("50.00"),
            net_amount=Decimal("45.00"),
            payed_out=False,
        )
        # Link via PayoutItem - let save() populate fields
        PayoutItem.objects.create(payout=payout, payment_transfer=tx)

        event_data = {
            "id": "evt_payout_paid",
            "type": "payout.paid",
            "data": {
                "object": {
                    "id": "po_existing",
                    "status": "paid",
                    "amount": 5000,
                    "currency": "usd",
                    "arrival_date": 1234567890,
                    "metadata": {"seller_id": str(self.seller.id)},
                }
            },
        }

        mock_construct_event.return_value = MagicMock(
            id="evt_payout_paid",
            type="payout.paid",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        with override_settings(STRIPE_WEBHOOK_CONNECT_SECRET="whsec_connect"):
            response = self.client.post(
                reverse("payment_system:stripe_webhook_connect"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )

        self.assertEqual(response.status_code, 200)

        payout.refresh_from_db()
        self.assertEqual(payout.status, "paid")

        tx.refresh_from_db()
        self.assertTrue(tx.payed_out)  # Should be marked paid out

        # Check tracker created/updated
        self.assertTrue(
            PaymentTracker.objects.filter(
                transaction_type="payout", status="payout_success", user=self.seller
            ).exists()
        )

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_payout_failed(self, mock_construct_event):
        """Test payout failure and transaction reset."""
        payout = Payout.objects.create(
            stripe_payout_id="po_failed", seller=self.seller, amount_cents=5000, currency="USD", status="pending"
        )

        # Transaction previously marked paid out (e.g. optimistically or in previous attempt)
        tx = PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=self.order,
            status="released",
            gross_amount=Decimal("50.00"),
            net_amount=Decimal("45.00"),
            payed_out=True,  # Initially true
        )
        PayoutItem.objects.create(payout=payout, payment_transfer=tx)

        event_data = {
            "id": "evt_payout_failed",
            "type": "payout.failed",
            "data": {
                "object": {
                    "id": "po_failed",
                    "status": "failed",
                    "failure_code": "account_closed",
                    "failure_message": "Closed",
                    "metadata": {"seller_id": str(self.seller.id)},
                }
            },
        }

        mock_construct_event.return_value = MagicMock(
            id="evt_payout_failed",
            type="payout.failed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        with override_settings(STRIPE_WEBHOOK_CONNECT_SECRET="whsec_connect"):
            response = self.client.post(
                reverse("payment_system:stripe_webhook_connect"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )

        self.assertEqual(response.status_code, 200)

        payout.refresh_from_db()
        self.assertEqual(payout.status, "failed")
        self.assertEqual(payout.failure_code, "account_closed")

        tx.refresh_from_db()
        self.assertFalse(tx.payed_out)  # Should be reset to False

        self.assertTrue(
            PaymentTracker.objects.filter(transaction_type="payout", status="payout_failed", user=self.seller).exists()
        )

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_checkout_user_not_found(self, mock_construct_event):
        """Test checkout session completed with invalid user_id."""
        event_data = {
            "id": "evt_checkout_user_fail",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_user_fail",
                    "metadata": {"order_id": str(self.order.id), "user_id": str(uuid.uuid4())},  # Random UUID
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_checkout_user_fail",
            type="checkout.session.completed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        # handle_sucessfull_checkout returns False, but webhook view returns 200 for checkout.session.completed even if logic fails (it logs error)
        # Wait, looking at views.py:
        # handle_sucessfull_checkout(checkout_session)
        # return HttpResponse(status=200, ...)
        self.assertEqual(response.status_code, 200)

        # Verify order NOT updated
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending_payment")

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_checkout_order_not_found(self, mock_construct_event):
        """Test checkout session completed with invalid order_id."""
        event_data = {
            "id": "evt_checkout_order_fail",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_order_fail",
                    "metadata": {"order_id": str(uuid.uuid4()), "user_id": str(self.buyer.id)},
                }
            },
        }
        mock_construct_event.return_value = MagicMock(
            id="evt_checkout_order_fail",
            type="checkout.session.completed",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_sig",
        )
        self.assertEqual(response.status_code, 200)

    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_connect_webhook_payout_create_fail_seller_not_found(self, mock_construct_event):
        """Test payout creation failure when seller is not found."""
        payout_id = "po_no_seller"
        event_data = {
            "id": "evt_payout_paid_no_seller",
            "type": "payout.paid",
            "data": {
                "object": {
                    "id": payout_id,
                    "status": "paid",
                    "amount": 5000,
                    "currency": "usd",
                    "arrival_date": 1234567890,
                    "metadata": {"seller_id": str(uuid.uuid4())},  # Invalid seller
                }
            },
        }

        mock_construct_event.return_value = MagicMock(
            id="evt_payout_paid_no_seller",
            type="payout.paid",
            data=MagicMock(object=self._to_object(event_data["data"]["object"])),
        )

        with override_settings(STRIPE_WEBHOOK_CONNECT_SECRET="whsec_connect"):
            # The view logs error but returns 200 for connect webhooks usually?
            # update_payout_from_webhook calls create_payout_from_webhook.
            # If create fails (returns None), update_payout_from_webhook raises TransactionError.
            # The view catches Exception and logs it, but returns 200.
            response = self.client.post(
                reverse("payment_system:stripe_webhook_connect"),
                json.dumps(event_data).encode("utf-8"),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid_sig",
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payout.objects.filter(stripe_payout_id=payout_id).exists())
