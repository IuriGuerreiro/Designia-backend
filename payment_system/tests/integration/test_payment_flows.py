"""
Payment System Tests - Integration

Tests covering end-to-end payment flows including Checkout, Webhooks, and Payouts.
Uses MockPaymentProvider to avoid real Stripe calls.

Story 4.6: Payment Integration Tests
"""

from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from infrastructure.payments.interface import CheckoutSession, PaymentIntent, PaymentStatus, WebhookEvent
from marketplace.models import Cart, Order, Product
from marketplace.services.order_service import OrderService
from payment_system.models import PaymentTransaction
from payment_system.services.checkout_service import CheckoutService
from payment_system.services.payout_service import PayoutService
from payment_system.services.webhook_service import WebhookService

User = get_user_model()


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
class PaymentIntegrationTest(TestCase):
    def setUp(self):
        # Users
        self.buyer = User.objects.create_user(username="buyer", email="buyer@example.com", password="password")
        self.seller = User.objects.create_user(username="seller", email="seller@example.com", password="password")
        self.seller.stripe_account_id = "acct_seller123"
        self.seller.save()

        # Product
        self.product = Product.objects.create(
            name="Test Product", price=Decimal("100.00"), seller=self.seller, stock_quantity=10
        )

        # Cart
        self.cart = Cart.objects.create(user=self.buyer)
        self.cart.items.create(product=self.product, quantity=1)

        # Mocks
        self.mock_provider = MagicMock()

        # Services with injected mock provider
        self.checkout_service = CheckoutService()
        # We need to patch the provider inside the services or use dependency injection container
        # Since services instantiate provider if None, we'll patch the container or provider getter

        # Patch Container.get_payment_provider globally for the test execution context
        # But better to inject mock into services if testing services directly.
        # For integration tests hitting Views, we need to patch where Views get Services or where Services get Provider.

        # For now, we test Services orchestrating together in a flow, mimicking View logic.

        self.webhook_service = WebhookService(payment_provider=self.mock_provider)
        self.payout_service = PayoutService(payment_provider=self.mock_provider)
        self.checkout_service.payment_service.payment_provider = self.mock_provider
        self.webhook_service.payment_service.payment_provider = self.mock_provider  # Ensure shared service uses mock

    def test_checkout_flow_success(self):
        """
        Test complete checkout flow:
        1. Create Order (simulated view logic)
        2. Create Checkout Session
        3. Process Webhook (Checkout Completed)
        4. Verify Order Paid
        """
        # 1. Create Order (simulated from Cart)
        order_service = OrderService()
        order_result = order_service.create_order(self.buyer, shipping_address={"line1": "123 Main"})
        self.assertTrue(order_result.ok)
        order = order_result.value

        self.assertEqual(order.status, "pending_payment")
        # Total includes product (100) + shipping/tax (20) = 120
        self.assertEqual(order.total_amount, Decimal("120.00"))

        # 2. Create Checkout Session
        mock_session = CheckoutSession(
            session_id="cs_test_123",
            url="http://checkout.url",
            amount=10000,
            currency="usd",
            status=PaymentStatus.PENDING,
            metadata={"order_id": str(order.id)},
        )
        self.mock_provider.create_checkout_session.return_value = mock_session

        checkout_result = self.checkout_service.create_checkout_session(order, "http://success", "http://cancel")
        self.assertTrue(checkout_result.ok)
        self.assertEqual(checkout_result.value.session_id, "cs_test_123")

        # 3. Process Webhook (Checkout Completed)
        event = WebhookEvent(
            event_id="evt_checkout_completed",
            event_type="checkout.session.completed",
            data={
                "object": {
                    "id": "cs_test_123",
                    "metadata": {"order_id": str(order.id)},
                    "payment_intent": "pi_test_123",
                }
            },
            created_at=1234567890,
        )
        self.mock_provider.verify_webhook.return_value = event

        # Mock retrieve payment intent for confirmation
        self.mock_provider.retrieve_payment_intent.return_value = PaymentIntent(
            intent_id="pi_test_123",
            amount=10000,
            currency="usd",
            status=PaymentStatus.SUCCEEDED,
            metadata={"order_id": str(order.id)},
        )

        webhook_result = self.webhook_service.process_webhook(b"raw_payload", "sig_header")
        self.assertTrue(webhook_result.ok)

        # 4. Verify Order Paid
        order.refresh_from_db()
        self.assertEqual(order.status, "payment_confirmed")  # Status updated by confirm_payment
        self.assertEqual(order.payment_status, "paid")

    def test_checkout_flow_failure(self):
        """
        Test failed payment flow:
        1. Create Order
        2. Process Webhook (Payment Failed)
        3. Verify Order Cancelled & Inventory Released
        """
        # Setup Order
        order = Order.objects.create(
            buyer=self.buyer,
            status="pending_payment",
            payment_status="processing",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            shipping_address={},
        )

        # Create item
        from marketplace.models import OrderItem

        OrderItem.objects.create(
            order=order,
            product=self.product,
            seller=self.product.seller,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
            product_name=self.product.name,
            product_description="desc",
        )

        # Reduce stock to simulate reservation
        self.product.stock_quantity = 9
        self.product.save()

        # Webhook: Payment Failed
        event = WebhookEvent(
            event_id="evt_payment_failed",
            event_type="payment_intent.payment_failed",
            data={
                "object": {
                    "id": "pi_fail",
                    "metadata": {"order_id": str(order.id)},
                    "last_payment_error": {"message": "Insufficient funds"},
                }
            },
            created_at=1234567890,
        )
        self.mock_provider.verify_webhook.return_value = event

        webhook_result = self.webhook_service.process_webhook(b"payload", "sig")
        self.assertTrue(webhook_result.ok)

        # Verify Order Cancelled
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

        # Verify Inventory Released
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)  # 9 + 1

    def test_payout_flow(self):
        """
        Test payout calculation and creation:
        1. Create completed PaymentTransactions
        2. Calculate Payout
        3. Create Payout
        4. Verify Payout Record and Transfer
        """
        # 1. Create Transactions
        order = Order.objects.create(buyer=self.buyer, total_amount=100, subtotal=100, shipping_address={})
        t1 = PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="completed",
            payed_out=False,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            stripe_payment_intent_id="pi_1",
            stripe_checkout_session_id="cs_1",
        )
        # Net should be 90.00

        # 2. Calculate Payout
        calc_result = self.payout_service.calculate_payout(self.seller)
        self.assertTrue(calc_result.ok)
        self.assertEqual(calc_result.value, Decimal("90.00"))

        # 3. Create Payout
        self.mock_provider.create_transfer.return_value = {"id": "tr_payout_123"}

        create_result = self.payout_service.create_payout(self.seller)
        self.assertTrue(create_result.ok)
        payout = create_result.value

        # 4. Verify
        self.assertEqual(payout.status, "paid")
        self.assertEqual(payout.amount_decimal, Decimal("90.00"))
        self.assertEqual(payout.stripe_payout_id, "tr_payout_123")

        t1.refresh_from_db()
        self.assertTrue(t1.payed_out)

    def test_idempotency_duplicate_webhooks(self):
        """Test that duplicate webhooks don't double-process."""
        # Setup paid order
        order = Order.objects.create(
            buyer=self.buyer,
            status="confirmed",
            payment_status="paid",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            shipping_address={},
        )

        event = WebhookEvent(
            event_id="evt_dup",
            event_type="payment_intent.succeeded",
            data={"object": {"id": "pi_dup", "metadata": {"order_id": str(order.id)}, "status": "succeeded"}},
            created_at=123,
        )
        self.mock_provider.verify_webhook.return_value = event
        self.mock_provider.retrieve_payment_intent.return_value = PaymentIntent(
            intent_id="pi_dup",
            amount=10000,
            currency="usd",
            status=PaymentStatus.SUCCEEDED,
            metadata={"order_id": str(order.id)},
        )

        # Process first time
        res1 = self.webhook_service.process_webhook(b"p", "s")
        self.assertTrue(res1.ok)

        # Process second time
        # OrderService logic handles idempotency by checking state
        res2 = self.webhook_service.process_webhook(b"p", "s")
        self.assertTrue(res2.ok)

        # Verify no errors and order remains paid
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
