"""
Tests for PayoutService

Story 4.4
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from infrastructure.payments.interface import PaymentProviderInterface
from marketplace.services.base import ErrorCodes
from payment_system.models import PaymentTransaction
from payment_system.services.payout_service import PayoutService

User = get_user_model()


class PayoutServiceTest(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(username="seller", email="seller@example.com", password="password")
        # Mock stripe_account_id on user (assuming it's patched or model has it)
        # Since user model is generic, we might need to monkeypatch it or use profile.
        self.seller.stripe_account_id = "acct_123"

        self.buyer = User.objects.create_user(username="buyer", email="buyer@example.com", password="password")

        self.mock_provider = MagicMock(spec=PaymentProviderInterface)
        self.service = PayoutService(payment_provider=self.mock_provider)

    def test_calculate_payout_sum(self):
        # Create transactions
        # Need Order for FK.
        from marketplace.models import Order

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})

        # Let's start fresh
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),  # Net: 90.00
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        )
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            gross_amount=Decimal("50.00"),
            platform_fee=Decimal("5.00"),  # Net: 45.00
            stripe_payment_intent_id="pi_2",
            stripe_checkout_session_id="cs_2",
        )
        # Ignored transaction (already paid)
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=True,
            gross_amount=Decimal("10.00"),
            platform_fee=Decimal("1.00"),  # Net: 9.00
            stripe_payment_intent_id="pi_3",
            stripe_checkout_session_id="cs_3",
        )

        result = self.service.calculate_payout(self.seller)

        self.assertTrue(result.ok)
        self.assertEqual(result.value, Decimal("135.00"))  # 90 + 45

    def test_create_payout_success(self):
        # Setup data
        from marketplace.models import Order

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})

        transaction_to_check_id = PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),  # Net: 90.00
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        ).id

        # Mock provider transfer
        self.mock_provider.create_transfer.return_value = {"id": "tr_123"}

        result = self.service.create_payout(self.seller)

        self.assertTrue(result.ok)
        payout = result.value

        self.assertEqual(payout.status, "paid")
        self.assertEqual(payout.amount_decimal, Decimal("90.00"))
        self.assertEqual(payout.stripe_payout_id, "tr_123")

        # Verify transaction updated
        transaction_from_db = PaymentTransaction.objects.get(id=transaction_to_check_id)
        self.assertTrue(transaction_from_db.payed_out)

        # Verify provider called
        self.mock_provider.create_transfer.assert_called_once_with(
            amount=Decimal("90.00"),
            currency="usd",
            destination_account="acct_123",
            metadata={"payout_id": str(payout.id)},
        )

    def test_create_payout_no_funds(self):
        result = self.service.create_payout(self.seller)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_OPERATION)

    def test_create_payout_no_stripe_account(self):
        self.seller.stripe_account_id = None

        from marketplace.models import Order

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("90.00"),
            gross_amount=100,
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        )

        result = self.service.create_payout(self.seller)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_PAYMENT_DATA)

    def test_create_payout_amount_mismatch(self):
        from marketplace.models import Order

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("50.00"),
            gross_amount=50,
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        )

        result = self.service.create_payout(self.seller, amount=Decimal("10.00"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.INVALID_OPERATION)

    def test_create_payout_provider_error(self):
        from marketplace.models import Order

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("50.00"),
            gross_amount=50,
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        )

        self.mock_provider.create_transfer.side_effect = Exception("Provider failed")

        result = self.service.create_payout(self.seller)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.PAYMENT_PROVIDER_ERROR)

    @patch("payment_system.services.payout_service.PayoutService.create_payout")
    def test_process_pending_payouts(self, mock_create_payout):
        from marketplace.models import Order
        from marketplace.services.base import service_ok

        mock_create_payout.return_value = service_ok("payout_obj")

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})

        # Seller 1
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("50.00"),
            gross_amount=50,
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        )

        # Seller 2
        seller2 = User.objects.create_user(username="seller2", email="seller2@example.com", password="password")
        # We don't need stripe_account_id here because we mock create_payout
        PaymentTransaction.objects.create(
            seller=seller2,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("20.00"),
            gross_amount=20,
            stripe_payment_intent_id="pi_2",
            stripe_checkout_session_id="cs_2",
        )

        result = self.service.process_pending_payouts()

        self.assertTrue(result.ok)
        self.assertEqual(result.value, 2)  # 2 sellers processed
        self.assertEqual(mock_create_payout.call_count, 2)

    def test_calculate_payout_filtering(self):
        from datetime import timedelta

        from django.utils import timezone

        from marketplace.models import Order

        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})
        now = timezone.now()

        # Transaction 1 (Today)
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("50.00"),
            gross_amount=50,
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
            created_at=now,
        )

        # Transaction 2 (Yesterday)
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            net_amount=Decimal("30.00"),
            gross_amount=30,
            stripe_payment_intent_id="pi_2",
            stripe_checkout_session_id="cs_2",
            created_at=now - timedelta(days=1),
        )

        # Filter for today only
        result = self.service.calculate_payout(self.seller, period_start=now - timedelta(hours=1))
        self.assertTrue(result.ok)
        self.assertEqual(result.value, Decimal("50.00"))

        # Filter for yesterday only
        result = self.service.calculate_payout(self.seller, period_end=now - timedelta(hours=12))
        self.assertTrue(result.ok)
        self.assertEqual(result.value, Decimal("30.00"))
