import json
import uuid  # Import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import clear_url_caches, reverse  # Import clear_url_caches

from infrastructure.payments.interface import CheckoutSession, PaymentIntent, PaymentStatus, WebhookEvent
from marketplace.models import Order
from marketplace.services.order_service import OrderService
from marketplace.tests.factories import (
    CartFactory,
    CartItemFactory,
    OrderFactory,
    OrderItemFactory,
    ProductFactory,
    SellerFactory,
    UserFactory,
)
from payment_system.models import PaymentTracker, PaymentTransaction
from payment_system.services.checkout_service import CheckoutService
from payment_system.services.payout_service import PayoutService
from payment_system.services.webhook_service import WebhookService

User = get_user_model()


@override_settings(
    STRIPE_WEBHOOK_SECRET="whsec_test_secret",
    TAX_RATES={"default": Decimal("0.00")},
    SHIPPING_FLAT_RATE=Decimal("0.00"),
    ROOT_URLCONF="designiaBackend.urls",  # Explicitly set URLConf for tests
)
class PaymentIntegrationTest(TestCase):
    def setUp(self):
        super().setUp()
        clear_url_caches()  # Clear URL caches for each test
        # Users
        self.buyer = UserFactory(username="buyer", email="buyer@example.com")
        self.seller = SellerFactory(username="seller", email="seller@example.com", stripe_account_id="acct_seller123")

        # Product
        self.product = ProductFactory(
            name="Test Product", price=Decimal("100.00"), seller=self.seller, stock_quantity=10
        )

        # Cart
        self.cart = CartFactory(user=self.buyer)
        CartItemFactory(cart=self.cart, product=self.product, quantity=1)

        # Mocks
        self.mock_provider = MagicMock()

        # Patch container to return mock provider
        self.provider_patcher = patch(
            "infrastructure.container.Container.get_payment_provider", return_value=self.mock_provider
        )
        self.provider_patcher.start()

        # Services (will pick up mock provider from Container)
        self.checkout_service = CheckoutService()
        self.webhook_service = WebhookService()
        self.payout_service = PayoutService()

        # Ensure provider is set on internal payment_service if cached/initialized early
        if hasattr(self.checkout_service, "payment_service"):
            self.checkout_service.payment_service.payment_provider = self.mock_provider
        if hasattr(self.webhook_service, "payment_service"):
            self.webhook_service.payment_service.payment_provider = self.mock_provider

    def tearDown(self):
        self.provider_patcher.stop()

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
        # Total includes product (100) + shipping/tax (0 in test env usually, but check) = 100
        self.assertEqual(order.total_amount, Decimal("100.00"))

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
        # Setup Order using factory
        order = OrderFactory(
            buyer=self.buyer,
            status="pending_payment",
            payment_status="processing",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )

        # Create item
        OrderItemFactory(
            order=order,
            product=self.product,
            seller=self.product.seller,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
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
        # Note: Default webhook logic might not automatically cancel order on failure unless configured
        # But assuming logic exists or we implement it.
        # For this test, let's see if webhook service handles it.
        # If not, we might need to update this expectation or the service.
        # Based on existing test, it expects 'cancelled'.
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
        order = OrderFactory(buyer=self.buyer, total_amount=100, subtotal=100)
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
        order = OrderFactory(
            buyer=self.buyer,
            status="confirmed",
            payment_status="paid",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
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

    @override_settings(STRIPE_WEBHOOK_SECRET=None)
    def test_webhook_missing_secret(self):
        """Test webhook processing when STRIPE_WEBHOOK_SECRET is not configured."""
        response = self.client.post(reverse("payment_system:stripe_webhook"), b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Webhook endpoint secret must be configured", response.content)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    def test_webhook_missing_signature(self):
        """Test webhook processing when stripe-signature header is missing."""
        response = self.client.post(reverse("payment_system:stripe_webhook"), b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Missing stripe-signature header", response.content)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_invalid_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")  # Patch at the view level
    def test_webhook_invalid_signature(self, mock_construct_event):
        """Test webhook processing with an invalid stripe-signature."""
        payload = b'{"id": "evt_test", "type": "payment_intent.succeeded"}'
        signature = "t=123,v1=invalid_signature"  # Malformed or invalid signature
        # Configure the mocked construct_event to raise the SignatureVerificationError
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", signature, payload
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Webhook signature verification failed.", response.content)
        mock_construct_event.assert_called_once()  # Ensure it was called

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.handle_sucessfull_checkout")
    @patch("payment_system.views.stripe.checkout.Session.retrieve")  # Patch for fallback
    def test_webhook_checkout_session_completed_missing_user_id_fallback_success(
        self, mock_retrieve_session, mock_handle_success, mock_construct_event
    ):
        """Test processing of checkout.session.completed webhook where user_id is missing initially,
        but found after retrieving the full session."""
        session_id = "cs_test_session_456"
        order = OrderFactory(buyer=self.buyer, status="pending_payment")

        # Mock event where initial metadata is missing user_id
        event_data_initial = {
            "id": "evt_checkout_completed_fallback",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "metadata": {"order_id": str(order.id)},  # Missing user_id
                    "payment_intent": "pi_checkout_fallback",
                }
            },
            "created": 1234567891,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data_initial["id"],
            type=event_data_initial["type"],
            created=event_data_initial["created"],
            data=MagicMock(
                object=MagicMock(
                    id=session_id,
                    metadata={"order_id": str(order.id)},
                    payment_intent="pi_checkout_fallback",
                )
            ),
        )

        # Mock the retrieved full session to have the user_id
        mock_retrieve_session.return_value = MagicMock(
            id=session_id,
            metadata={"user_id": str(self.buyer.id), "order_id": str(order.id)},
            payment_intent="pi_checkout_fallback",
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data_initial).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_retrieve_session.assert_called_once_with(session_id)
        mock_handle_success.assert_called_once()
        self.assertEqual(mock_handle_success.call_args[0][0].id, session_id)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.handle_sucessfull_checkout")
    @patch("payment_system.views.stripe.checkout.Session.retrieve")  # Patch for fallback
    def test_webhook_checkout_session_completed_missing_user_id_fallback_fail(
        self, mock_retrieve_session, mock_handle_success, mock_construct_event
    ):
        """Test processing of checkout.session.completed webhook where user_id is missing
        both initially and after retrieving the full session."""
        session_id = "cs_test_session_789"
        order = OrderFactory(buyer=self.buyer, status="pending_payment")

        # Mock event where initial metadata is missing user_id
        event_data_initial = {
            "id": "evt_checkout_completed_fallback_fail",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "metadata": {"order_id": str(order.id)},  # Missing user_id
                    "payment_intent": "pi_checkout_fallback_fail",
                }
            },
            "created": 1234567892,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data_initial["id"],
            type=event_data_initial["type"],
            created=event_data_initial["created"],
            data=MagicMock(
                object=MagicMock(
                    id=session_id,
                    metadata={"order_id": str(order.id)},
                    payment_intent="pi_checkout_fallback_fail",
                )
            ),
        )

        # Mock the retrieved full session to *also* be missing the user_id
        mock_retrieve_session.return_value = MagicMock(
            id=session_id,
            metadata={"order_id": str(order.id)},  # Still missing user_id
            payment_intent="pi_checkout_fallback_fail",
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data_initial).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 400)  # Expecting a 400 because user_id is critical
        mock_construct_event.assert_called_once()
        mock_retrieve_session.assert_called_once_with(session_id)
        mock_handle_success.assert_not_called()  # Should not call handle_success if user_id not found

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.send_order_cancellation_receipt_email")
    @patch("marketplace.models.Order.objects.get")  # Mock Order.objects.get for specific scenarios
    def test_webhook_refund_updated_succeeded_no_order_id_in_metadata(
        self, mock_order_get, mock_send_email, mock_construct_event
    ):
        """Test successful refund.updated webhook when order_id is missing from metadata."""
        refund_id = "re_refund_no_order_id_123"
        refund_amount = 10000

        # Event data without order_id in metadata
        event_data = {
            "id": "evt_refund_updated_no_order_id",
            "type": "refund.updated",
            "data": {
                "object": {
                    "id": refund_id,
                    "status": "succeeded",
                    "amount": refund_amount,
                    "metadata": {},  # Missing order_id
                    "failure_balance_transaction": None,
                }
            },
            "created": 1234567893,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=refund_id,
                    status="succeeded",
                    amount=refund_amount,
                    metadata={},
                    failure_balance_transaction=None,
                )
            ),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)  # Webhook processing should still return 200
        mock_construct_event.assert_called_once()
        mock_order_get.assert_not_called()  # Order.objects.get should not be called
        mock_send_email.assert_not_called()  # Email should not be sent

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.send_order_cancellation_receipt_email")
    @patch("marketplace.models.Order.objects.get")
    def test_webhook_refund_updated_succeeded_order_not_found(
        self, mock_order_get, mock_send_email, mock_construct_event
    ):
        """Test successful refund.updated webhook when the associated order is not found."""
        order_id = str(uuid.uuid4())  # Non-existent order ID
        refund_id = "re_refund_order_not_found"
        refund_amount = 10000

        event_data = {
            "id": "evt_refund_updated_order_not_found",
            "type": "refund.updated",
            "data": {
                "object": {
                    "id": refund_id,
                    "status": "succeeded",
                    "amount": refund_amount,
                    "metadata": {"order_id": order_id},
                    "failure_balance_transaction": None,
                }
            },
            "created": 1234567894,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=refund_id,
                    status="succeeded",
                    amount=refund_amount,
                    metadata={"order_id": order_id},
                    failure_balance_transaction=None,
                )
            ),
        )
        mock_order_get.side_effect = Order.DoesNotExist  # Simulate Order not found

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)  # Webhook processing should still return 200
        mock_construct_event.assert_called_once()
        mock_order_get.assert_called_once_with(id=order_id)
        mock_send_email.assert_not_called()  # Email should not be sent

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.send_order_cancellation_receipt_email")
    @patch("marketplace.models.Order.objects.get")
    def test_webhook_refund_updated_succeeded(self, mock_order_get, mock_send_email, mock_construct_event):
        """Test processing of a successful refund.updated webhook."""
        order = OrderFactory(buyer=self.buyer, status="refunded", payment_status="refunded")
        # Ensure order.items exists and has a product
        OrderItemFactory(order=order, product=self.product, quantity=1)

        refund_id = "re_refund_success_123"
        refund_amount = 10000  # in cents

        # Create a PaymentTransaction that is waiting for refund
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="waiting_refund",
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("0.00"),
            stripe_payment_intent_id="pi_test_refund",
            stripe_checkout_session_id="cs_test_refund",
            net_amount=Decimal("100.00"),
        )

        event_data = {
            "id": "evt_refund_updated_success",
            "type": "refund.updated",
            "data": {
                "object": {
                    "id": refund_id,
                    "status": "succeeded",
                    "amount": refund_amount,
                    "metadata": {"order_id": str(order.id)},
                    "failure_balance_transaction": None,
                }
            },
            "created": 1234567892,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=refund_id,
                    status="succeeded",
                    amount=refund_amount,
                    metadata={"order_id": str(order.id)},
                    failure_balance_transaction=None,
                )
            ),
        )
        mock_order_get.return_value = order
        mock_send_email.return_value = (True, "Email sent")

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_order_get.assert_called_once_with(id=str(order.id))
        mock_send_email.assert_called_once()
        order.refresh_from_db()
        self.assertEqual(order.status, "refunded")
        self.assertEqual(order.payment_status, "refunded")
        self.assertTrue(PaymentTransaction.objects.filter(order=order, status="refunded").exists())

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.send_failed_refund_notification_email")
    @patch("marketplace.models.Order.objects.get")
    def test_webhook_refund_failed(self, mock_order_get, mock_send_email, mock_construct_event):
        """Test processing of a refund.failed webhook."""
        order = OrderFactory(buyer=self.buyer, status="refunded", payment_status="refunded")
        OrderItemFactory(order=order, product=self.product, quantity=1)

        # Create a PaymentTransaction that was awaiting refund for this order
        PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="waiting_refund",
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("0.00"),
            stripe_payment_intent_id="pi_failed_refund",
            stripe_checkout_session_id="cs_failed_refund",
            net_amount=Decimal("100.00"),
        )

        refund_id = "re_refund_failed_123"
        failure_reason = "insufficient_funds"
        refund_amount = 10000
        event_data = {
            "id": "evt_refund_failed",
            "type": "refund.failed",
            "data": {
                "object": {
                    "id": refund_id,
                    "status": "failed",
                    "amount": refund_amount,
                    "metadata": {"order_id": str(order.id)},
                    "failure_reason": failure_reason,
                }
            },
            "created": 1234567895,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=refund_id,
                    status="failed",
                    amount=refund_amount,
                    metadata={"order_id": str(order.id)},
                    failure_reason=failure_reason,
                )
            ),
        )
        mock_order_get.return_value = order
        mock_send_email.return_value = (True, "Email sent")

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_order_get.assert_called_once_with(id=str(order.id))
        mock_send_email.assert_called_once()
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")  # Order status should be cancelled
        self.assertEqual(order.payment_status, "failed_refund")  # Payment status should be failed_refund
        self.assertTrue(PaymentTransaction.objects.filter(order=order, status="failed_refund").exists())

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_transfer_created_success(self, mock_construct_event):
        """Test processing of a successful transfer.created webhook."""
        # Create an order and an order item to ensure product exists
        order = OrderFactory(buyer=self.buyer, status="payment_confirmed")
        OrderItemFactory(order=order, product=self.product, quantity=1)

        # Create a PaymentTransaction that is in 'processing' status (e.g., waiting for transfer to complete)
        payment_transaction = PaymentTransaction.objects.create(
            seller=self.seller,
            buyer=self.buyer,
            order=order,
            status="processing",  # Should be 'processing' for a transfer.created event
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("0.00"),
            stripe_payment_intent_id="pi_transfer_test",
            stripe_checkout_session_id="cs_transfer_test",
            net_amount=Decimal("100.00"),
            transfer_id="tr_some_temp_id",
        )

        transfer_id = "tr_transfer_success_123"
        amount = 10000
        currency = "usd"

        event_data = {
            "id": "evt_transfer_created_success",
            "type": "transfer.created",
            "data": {
                "object": {
                    "id": transfer_id,
                    "amount": amount,
                    "currency": currency,
                    "destination": self.seller.stripe_account_id,
                    "metadata": {
                        "transaction_id": str(payment_transaction.id),
                        "order_id": str(order.id),
                        "seller_id": str(self.seller.id),
                        "buyer_id": str(self.buyer.id),
                    },
                    "reversed": False,
                }
            },
            "created": 1234567896,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=transfer_id,
                    amount=amount,
                    currency=currency,
                    destination=self.seller.stripe_account_id,
                    metadata={
                        "transaction_id": str(payment_transaction.id),
                        "order_id": str(order.id),
                        "seller_id": str(self.seller.id),
                        "buyer_id": str(self.buyer.id),
                    },
                    reversed=False,
                )
            ),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        payment_transaction.refresh_from_db()
        self.assertEqual(payment_transaction.status, "released")  # Status should be released
        self.assertEqual(payment_transaction.transfer_id, transfer_id)
        expected_notes_prefix = (
            f"Transfer succeeded via webhook: {transfer_id} (amount: {amount/100:.2f} {currency.upper()})"
        )
        print(f"Actual notes: '{payment_transaction.notes}'")  # Debugging print
        self.assertTrue(payment_transaction.notes.endswith(expected_notes_prefix))
        self.assertTrue(PaymentTracker.objects.filter(stripe_transfer_id=transfer_id, status="succeeded").exists())

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.stripe_service.StripeConnectService.handle_account_updated_webhook")
    def test_webhook_account_updated(self, mock_handle_account_updated_webhook, mock_construct_event):
        """Test processing of an account.updated webhook."""
        account_id = self.seller.stripe_account_id
        event_data = {
            "id": "evt_account_updated",
            "type": "account.updated",
            "data": {
                "object": {
                    "id": account_id,
                    "charges_enabled": True,
                    "payouts_enabled": True,
                    "details_submitted": True,
                    "metadata": {},
                }
            },
            "created": 1234567897,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=account_id,
                    charges_enabled=True,
                    payouts_enabled=True,
                    details_submitted=True,
                    metadata={},
                )
            ),
        )
        mock_handle_account_updated_webhook.return_value = {
            "success": True,
            "user_id": str(self.seller.id),
        }

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_handle_account_updated_webhook.assert_called_once_with(
            account_id, mock_construct_event.return_value.data.object
        )

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.handle_payment_intent_succeeded")
    def test_webhook_payment_intent_succeeded(self, mock_handle_payment_intent_succeeded, mock_construct_event):
        """Test processing of a payment_intent.succeeded webhook."""
        payment_intent_id = "pi_payment_succeeded_test"
        amount = 10000
        currency = "usd"

        event_data = {
            "id": "evt_payment_intent_succeeded",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "amount": amount,
                    "currency": currency,
                    "status": "succeeded",
                }
            },
            "created": 1234567898,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=payment_intent_id,
                    amount=amount,
                    currency=currency,
                    status="succeeded",
                )
            ),
        )
        mock_handle_payment_intent_succeeded.return_value = {
            "success": True,
            "trackers_updated": 1,
            "transactions_updated": 1,
            "orders_updated": 1,
        }

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_handle_payment_intent_succeeded.assert_called_once_with(mock_construct_event.return_value.data.object)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    @patch("payment_system.views.handle_payment_intent_failed")
    def test_webhook_payment_intent_payment_failed(self, mock_handle_payment_intent_failed, mock_construct_event):
        """Test processing of a payment_intent.payment_failed webhook."""
        payment_intent_id = "pi_payment_failed_test"
        amount = 10000
        currency = "usd"
        failure_code = "card_declined"
        failure_message = "Your card was declined."

        event_data = {
            "id": "evt_payment_intent_payment_failed",
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "amount": amount,
                    "currency": currency,
                    "status": "failed",
                    "last_payment_error": {
                        "code": failure_code,
                        "message": failure_message,
                        "type": "card_error",
                    },
                }
            },
            "created": 1234567899,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(
                object=MagicMock(
                    id=payment_intent_id,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    last_payment_error=MagicMock(
                        code=failure_code,
                        message=failure_message,
                        type="card_error",
                    ),
                )
            ),
        )
        mock_handle_payment_intent_failed.return_value = {
            "success": True,
            "trackers_updated": 1,
            "transactions_updated": 1,
            "orders_updated": 1,
        }

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        mock_handle_payment_intent_failed.assert_called_once_with(mock_construct_event.return_value.data.object)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_secret")
    @patch("payment_system.views.stripe.Webhook.construct_event")
    def test_webhook_unhandled_event_type(self, mock_construct_event):
        """Test processing of an unhandled webhook event type."""
        event_data = {
            "id": "evt_unhandled_event",
            "type": "some.unhandled.event",
            "data": {"object": {"id": "obj_unhandled"}},
            "created": 1234567900,
        }
        mock_construct_event.return_value = MagicMock(
            id=event_data["id"],
            type=event_data["type"],
            created=event_data["created"],
            data=MagicMock(object=MagicMock(id="obj_unhandled")),
        )

        response = self.client.post(
            reverse("payment_system:stripe_webhook"),
            json.dumps(event_data).encode("utf-8"),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid_signature",
        )

        self.assertEqual(response.status_code, 200)
        mock_construct_event.assert_called_once()
        # No further processing should happen for unhandled events, so no other mocks should be called

    def test_create_checkout_session_empty_cart(self):
        """Test creating a checkout session with an empty cart."""
        self.cart.items.all().delete()  # Ensure the cart is empty

        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("payment_system:create_checkout_session"), data={}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("EMPTY_CART", response.json()["error"])
