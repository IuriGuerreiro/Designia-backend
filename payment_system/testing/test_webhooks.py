"""
Webhook testing scripts for Stripe CLI integration
"""

import json
import time
from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from marketplace.models import Order
from payment_system.models import Payment, SellerPayout, StripeAccount, WebhookEvent


User = get_user_model()


class StripeWebhookTestCase(TestCase):
    """Test Stripe webhook handling with CLI integration"""

    def setUp(self):
        """Set up test data for webhook testing"""
        self.buyer = User.objects.create_user(username="webhook_buyer", email="buyer@webhooktest.com")
        self.seller = User.objects.create_user(username="webhook_seller", email="seller@webhooktest.com")

        self.stripe_account = StripeAccount.objects.create(
            user=self.seller,
            stripe_account_id="acct_webhook_test",
            email=self.seller.email,
            country="US",
            is_active=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            shipping_address={
                "street": "123 Test St",
                "city": "Test City",
                "state": "TC",
                "postal_code": "12345",
                "country": "US",
            },
            status="pending",
        )

        # Create payment that will be updated by webhooks
        self.payment = Payment.objects.create(
            payment_intent_id="pi_webhook_test_123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("100.00"),
            status="processing",
        )

    def create_stripe_webhook_payload(self, event_type, data_object):
        """Create a realistic Stripe webhook payload"""
        return {
            "id": f"evt_{int(time.time())}",
            "object": "event",
            "api_version": "2020-08-27",
            "created": int(time.time()),
            "data": {"object": data_object},
            "livemode": False,
            "pending_webhooks": 1,
            "request": {"id": f"req_{int(time.time())}", "idempotency_key": None},
            "type": event_type,
        }

    @patch("stripe.Webhook.construct_event")
    def test_payment_intent_succeeded_webhook(self, mock_construct_event):
        """Test payment_intent.succeeded webhook"""
        # Create webhook payload
        payment_intent_data = {
            "id": "pi_webhook_test_123",
            "object": "payment_intent",
            "amount": 10000,  # $100.00 in cents
            "currency": "usd",
            "status": "succeeded",
            "metadata": {"order_id": str(self.order.id), "buyer_id": str(self.buyer.id)},
        }

        webhook_payload = self.create_stripe_webhook_payload("payment_intent.succeeded", payment_intent_data)

        mock_construct_event.return_value = webhook_payload

        # Send webhook to endpoint
        response = self.client.post(
            "/api/payments/webhooks/stripe/",
            data=json.dumps(webhook_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        # Verify payment was updated
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "succeeded")
        self.assertIsNotNone(self.payment.processed_at)

        # Verify webhook event was logged
        webhook_event = WebhookEvent.objects.get(stripe_event_id=webhook_payload["id"])
        self.assertEqual(webhook_event.event_type, "payment_intent.succeeded")
        self.assertEqual(webhook_event.status, "processed")

    @patch("stripe.Webhook.construct_event")
    def test_payment_intent_failed_webhook(self, mock_construct_event):
        """Test payment_intent.payment_failed webhook"""
        payment_intent_data = {
            "id": "pi_webhook_test_123",
            "object": "payment_intent",
            "status": "requires_payment_method",
            "last_payment_error": {
                "code": "card_declined",
                "decline_code": "generic_decline",
                "message": "Your card was declined.",
            },
        }

        webhook_payload = self.create_stripe_webhook_payload("payment_intent.payment_failed", payment_intent_data)

        mock_construct_event.return_value = webhook_payload

        response = self.client.post(
            "/api/payments/webhooks/stripe/",
            data=json.dumps(webhook_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        # Verify payment status was updated
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")

    @patch("stripe.Webhook.construct_event")
    def test_account_updated_webhook(self, mock_construct_event):
        """Test account.updated webhook for seller account status"""
        account_data = {
            "id": "acct_webhook_test",
            "object": "account",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
            "requirements": {"currently_due": [], "eventually_due": [], "past_due": [], "pending_verification": []},
        }

        webhook_payload = self.create_stripe_webhook_payload("account.updated", account_data)

        mock_construct_event.return_value = webhook_payload

        response = self.client.post(
            "/api/payments/webhooks/stripe/",
            data=json.dumps(webhook_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        # Verify Stripe account was updated
        self.stripe_account.refresh_from_db()
        self.assertTrue(self.stripe_account.charges_enabled)
        self.assertTrue(self.stripe_account.payouts_enabled)
        self.assertTrue(self.stripe_account.details_submitted)
        self.assertTrue(self.stripe_account.is_active)

    @patch("stripe.Webhook.construct_event")
    def test_transfer_created_webhook(self, mock_construct_event):
        """Test transfer.created webhook for seller payouts"""
        # Create a payout that will be updated
        payout = SellerPayout.objects.create(
            payment=self.payment,
            seller=self.seller,
            stripe_account=self.stripe_account,
            amount=Decimal("95.00"),
            application_fee=Decimal("5.00"),
            status="pending",
        )

        transfer_data = {
            "id": "tr_webhook_test_123",
            "object": "transfer",
            "amount": 9500,  # $95.00 in cents
            "currency": "usd",
            "destination": "acct_webhook_test",
            "metadata": {
                "payout_id": str(payout.id),
                "order_id": str(self.order.id),
                "seller_id": str(self.seller.id),
            },
        }

        webhook_payload = self.create_stripe_webhook_payload("transfer.created", transfer_data)

        mock_construct_event.return_value = webhook_payload

        response = self.client.post(
            "/api/payments/webhooks/stripe/",
            data=json.dumps(webhook_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        # Verify payout was updated
        payout.refresh_from_db()
        self.assertEqual(payout.status, "processing")
        self.assertEqual(payout.stripe_transfer_id, "tr_webhook_test_123")

    def test_webhook_signature_verification_failure(self):
        """Test webhook with invalid signature"""
        webhook_payload = self.create_stripe_webhook_payload("payment_intent.succeeded", {"id": "pi_test"})

        response = self.client.post(
            "/api/payments/webhooks/stripe/",
            data=json.dumps(webhook_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="invalid_signature",
        )

        self.assertEqual(response.status_code, 400)

    def test_webhook_unknown_event_type(self):
        """Test webhook with unknown event type"""
        with patch("stripe.Webhook.construct_event") as mock_construct_event:
            webhook_payload = self.create_stripe_webhook_payload("unknown.event.type", {"id": "test_object"})

            mock_construct_event.return_value = webhook_payload

            response = self.client.post(
                "/api/payments/webhooks/stripe/",
                data=json.dumps(webhook_payload),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="test_signature",
            )

            self.assertEqual(response.status_code, 200)

            # Verify event was logged but ignored
            webhook_event = WebhookEvent.objects.get(stripe_event_id=webhook_payload["id"])
            self.assertEqual(webhook_event.status, "ignored")


class StripeCliIntegrationTestCase(TestCase):
    """Test Stripe CLI integration and webhook forwarding"""

    def setUp(self):
        self.webhook_url = "http://localhost:8000/api/payments/webhooks/stripe/"

    @override_settings(DEBUG=True)
    def test_webhook_endpoint_accessibility(self):
        """Test that webhook endpoint is accessible for CLI forwarding"""
        # This test ensures the webhook endpoint is properly configured
        # for Stripe CLI forwarding
        response = self.client.post("/api/payments/webhooks/stripe/", data="{}", content_type="application/json")

        # Should return 400 due to invalid signature, not 404
        self.assertIn(response.status_code, [400, 500])  # Not 404

    def test_webhook_cors_headers(self):
        """Test CORS headers for webhook endpoint"""
        response = self.client.options("/api/payments/webhooks/stripe/")

        # Webhook endpoint should be accessible for Stripe
        self.assertNotEqual(response.status_code, 404)


class WebhookTestUtilities:
    """Utility functions for webhook testing"""

    @staticmethod
    def simulate_stripe_cli_webhook(event_type, data_object, webhook_url=None):
        """Simulate a webhook sent by Stripe CLI"""
        if not webhook_url:
            webhook_url = "http://localhost:8000/api/payments/webhooks/stripe/"

        webhook_payload = {
            "id": f"evt_cli_test_{int(time.time())}",
            "object": "event",
            "api_version": "2020-08-27",
            "created": int(time.time()),
            "data": {"object": data_object},
            "livemode": False,
            "pending_webhooks": 1,
            "request": {"id": f"req_cli_test_{int(time.time())}"},
            "type": event_type,
        }

        try:
            response = requests.post(
                webhook_url,
                json=webhook_payload,
                headers={"Content-Type": "application/json", "Stripe-Signature": "test_signature_from_cli"},
                timeout=30,
            )
            return response
        except requests.exceptions.RequestException as e:
            print(f"Webhook simulation failed: {e}")
            return None

    @staticmethod
    def create_test_payment_intent_data(payment_intent_id, amount_cents=10000):
        """Create test PaymentIntent data for webhooks"""
        return {
            "id": payment_intent_id,
            "object": "payment_intent",
            "amount": amount_cents,
            "currency": "usd",
            "status": "succeeded",
            "metadata": {"marketplace": "designia", "test_webhook": "true"},
        }

    @staticmethod
    def create_test_account_data(account_id):
        """Create test Account data for webhooks"""
        return {
            "id": account_id,
            "object": "account",
            "business_type": "individual",
            "charges_enabled": True,
            "country": "US",
            "payouts_enabled": True,
            "details_submitted": True,
        }

    @staticmethod
    def create_test_transfer_data(transfer_id, amount_cents, destination_account):
        """Create test Transfer data for webhooks"""
        return {
            "id": transfer_id,
            "object": "transfer",
            "amount": amount_cents,
            "currency": "usd",
            "destination": destination_account,
            "metadata": {"marketplace": "designia", "test_webhook": "true"},
        }


# Manual testing functions for CLI integration
def run_manual_webhook_tests():
    """Run manual webhook tests with Stripe CLI"""
    print("🧪 Manual Webhook Testing Guide")
    print("=" * 50)
    print()
    print("Prerequisites:")
    print("1. Run: stripe login")
    print("2. Start Django server: python manage.py runserver")
    print("3. Start webhook forwarding: stripe listen --forward-to localhost:8000/api/payments/webhooks/stripe/")
    print()
    print("Test Commands:")
    print("1. Test payment success:")
    print("   stripe trigger payment_intent.succeeded")
    print()
    print("2. Test payment failure:")
    print("   stripe trigger payment_intent.payment_failed")
    print()
    print("3. Test account update:")
    print("   stripe trigger account.updated")
    print()
    print("4. Test transfer creation:")
    print("   stripe trigger transfer.created")
    print()
    print("5. Test custom webhook:")
    print("   stripe events resend evt_YOUR_EVENT_ID")
    print()
    print("Verification:")
    print("- Check Django console for webhook processing logs")
    print("- Verify WebhookEvent objects in admin")
    print("- Confirm payment/account status updates")


if __name__ == "__main__":
    print("Stripe Webhook Testing Utilities")
    print("Available functions:")
    print("- WebhookTestUtilities.simulate_stripe_cli_webhook()")
    print("- run_manual_webhook_tests()")
    print()
    run_manual_webhook_tests()
