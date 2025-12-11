"""
Tests for Payment Error Handling and Recovery

Story 4.7
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase

from infrastructure.payments.stripe_provider import StripeProvider


User = get_user_model()


class ErrorRecoveryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", email="user@test.com")
        self.provider = StripeProvider()

        # Mock stripe to simulate errors
        self.patcher = patch("stripe.checkout.Session.create")
        self.mock_create = self.patcher.start()

        # Mock time.sleep to speed up tenacity retries
        self.sleep_patcher = patch("time.sleep")
        self.mock_sleep = self.sleep_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.sleep_patcher.stop()

    def test_retry_on_rate_limit_error(self):
        """Test that network calls retry on RateLimitError."""
        # Configure mock to raise RateLimitError twice, then succeed
        self.mock_create.side_effect = [
            stripe.error.RateLimitError("Rate limit exceeded", http_status=429),
            stripe.error.RateLimitError("Rate limit exceeded", http_status=429),
            MagicMock(
                id="sess_123",
                url="http://url",
                payment_status="unpaid",
                amount_total=1000,
                currency="usd",
                metadata={},
            ),
        ]

        # Call method decorated with @retry
        # Note: tenacity waits are real unless mocked, but we use small wait or mock time
        # We rely on tenacity configuration (min=2) which might slow down test.
        # Ideally patch wait or time.sleep.

        # For integration test speed, we assume tenacity works but check if result is success eventually.
        # Or we can check call count.

        session = self.provider.create_checkout_session(
            amount=Decimal("10.00"), currency="usd", success_url="s", cancel_url="c"
        )

        self.assertEqual(session.session_id, "sess_123")
        self.assertEqual(self.mock_create.call_count, 3)

    def test_fail_after_retries(self):
        """Test that it fails after max retries."""
        self.mock_create.side_effect = stripe.error.APIConnectionError("Connection failed")

        from infrastructure.payments.interface import PaymentException

        with self.assertRaises(PaymentException):  # Provider wraps exception
            self.provider.create_checkout_session(
                amount=Decimal("10.00"), currency="usd", success_url="s", cancel_url="c"
            )

        # Should be 3 calls (stop_after_attempt(3))
        self.assertEqual(self.mock_create.call_count, 3)

    def test_no_retry_on_invalid_request(self):
        """Test that logic errors are NOT retried."""
        self.mock_create.side_effect = stripe.error.InvalidRequestError("Invalid param", param="foo")

        from infrastructure.payments.interface import PaymentException

        with self.assertRaises(PaymentException):
            self.provider.create_checkout_session(
                amount=Decimal("10.00"), currency="usd", success_url="s", cancel_url="c"
            )

        self.assertEqual(self.mock_create.call_count, 1)
