"""
Test webhook security fixes to ensure signature verification is working correctly.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase


class WebhookSecurityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.webhook_url = "/api/payments/stripe_webhook/"
        self.test_secret = "whsec_test_secret_key_for_testing"
        self.test_payload = {
            "id": "evt_test_webhook",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_session", "metadata": {"user_id": "123"}}},
        }

    def generate_stripe_signature(self, payload, secret, timestamp=None):
        """Generate a valid Stripe signature for testing"""
        if timestamp is None:
            timestamp = int(time.time())

        payload_str = json.dumps(payload, separators=(",", ":"))
        signed_payload = f"{timestamp}.{payload_str}"
        signature = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        return f"t={timestamp},v1={signature}"

    @patch("payment_system.views.settings.STRIPE_WEBHOOK_SECRET", None)
    def test_webhook_rejects_when_no_secret_configured(self):
        """Test that webhook rejects requests when no secret is configured"""
        response = self.client.post(
            self.webhook_url, data=json.dumps(self.test_payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Webhook endpoint secret must be configured", response.content)

    @patch("payment_system.views.settings.STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    def test_webhook_rejects_missing_signature_header(self):
        """Test that webhook rejects requests without signature header"""
        response = self.client.post(
            self.webhook_url, data=json.dumps(self.test_payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Missing stripe-signature header", response.content)

    @patch("payment_system.views.settings.STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    def test_webhook_rejects_invalid_signature(self):
        """Test that webhook rejects requests with invalid signature"""
        response = self.client.post(
            self.webhook_url,
            data=json.dumps(self.test_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234567890,v1=invalid_signature",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Webhook signature verification failed", response.content)

    @patch("payment_system.views.settings.STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    @patch("stripe.Webhook.construct_event")
    def test_webhook_accepts_valid_signature(self, mock_construct_event):
        """Test that webhook accepts requests with valid signature"""
        # Mock successful signature verification - return object with attributes
        mock_event = type(
            "Event",
            (),
            {
                "type": "checkout.session.completed",
                "data": type("Data", (), {"object": self.test_payload["data"]["object"]})(),
            },
        )()
        mock_construct_event.return_value = mock_event

        valid_signature = self.generate_stripe_signature(self.test_payload, "test_secret")

        response = self.client.post(
            self.webhook_url,
            data=json.dumps(self.test_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=valid_signature,
        )

        # Should not reject due to signature issues
        self.assertNotEqual(response.status_code, 400)
        # construct_event should be called for signature verification
        mock_construct_event.assert_called_once()

    @patch("payment_system.views.settings.STRIPE_WEBHOOK_SECRET", None)
    def test_webhook_logs_security_events(self):
        """Test that security events are properly logged"""
        with self.assertLogs("payment_system.views", level="ERROR") as log:
            response = self.client.post(
                self.webhook_url, data=json.dumps(self.test_payload), content_type="application/json"
            )

            self.assertEqual(response.status_code, 500)
            self.assertIn("STRIPE_WEBHOOK_SECRET not configured", log.output[0])

    @patch("payment_system.views.settings.STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    def test_webhook_logs_signature_failures(self):
        """Test that signature verification failures are logged with IP"""
        with self.assertLogs("payment_system.views", level="WARNING") as log:
            response = self.client.post(
                self.webhook_url,
                data=json.dumps(self.test_payload),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1234567890,v1=invalid_signature",
                REMOTE_ADDR="192.168.1.100",
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn("signature verification failed", log.output[0])
            self.assertIn("192.168.1.100", log.output[0])


if __name__ == "__main__":
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "payment_system",
            ],
            SECRET_KEY="test-secret-key-for-testing-only",
        )

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["__main__"])
