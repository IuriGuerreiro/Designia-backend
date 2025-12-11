"""
Unit tests for payment system models
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from marketplace.models import Order, OrderItem, Product
from payment_system.models import Payment, PaymentTransaction, RefundRequest, SellerPayout, StripeAccount, WebhookEvent


User = get_user_model()


class PaymentModelTestCase(TestCase):
    def setUp(self):
        """Set up test data"""
        # Create test users
        self.buyer = User.objects.create_user(username="testbuyer", email="buyer@test.com", password="testpass123")
        self.seller = User.objects.create_user(username="testseller", email="seller@test.com", password="testpass123")

        # Create Stripe account for seller
        self.stripe_account = StripeAccount.objects.create(
            user=self.seller,
            stripe_account_id="acct_test123",
            email=self.seller.email,
            country="US",
            is_active=True,
            charges_enabled=True,
            payouts_enabled=True,
        )

        # Create test product and order
        self.product = Product.objects.create(
            name="Test Product", description="A test product", price=Decimal("99.99"), seller=self.seller
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("99.99"),
            total_amount=Decimal("99.99"),
            shipping_address={
                "street": "123 Test St",
                "city": "Test City",
                "state": "TC",
                "postal_code": "12345",
                "country": "US",
            },
            status="pending",
        )

        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=self.seller,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
            product_name=self.product.name,
            product_description=self.product.description,
        )

    def test_stripe_account_creation(self):
        """Test StripeAccount model creation and validation"""
        # Test successful creation
        self.assertEqual(self.stripe_account.user, self.seller)
        self.assertEqual(self.stripe_account.stripe_account_id, "acct_test123")
        self.assertTrue(self.stripe_account.is_active)
        self.assertEqual(str(self.stripe_account), f"Stripe Account for {self.seller.username}")

    def test_payment_automatic_hold_setting(self):
        """Test that payments automatically set 30-day hold period"""
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            application_fee=Decimal("5.00"),
            status="succeeded",
        )

        # Check that hold_until is automatically set to 30 days from creation
        self.assertIsNotNone(payment.hold_until)
        expected_hold_date = payment.created_at + timedelta(days=30)
        self.assertEqual(payment.hold_until.date(), expected_hold_date.date())
        self.assertTrue(payment.is_held)
        self.assertIsNone(payment.hold_released_at)

    def test_payment_hold_release_eligibility(self):
        """Test payment hold release eligibility checking"""
        # Create payment with past hold date
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            application_fee=Decimal("5.00"),
            status="succeeded",
            hold_until=timezone.now() - timedelta(days=1),  # Past due
        )

        # Should be eligible for release
        self.assertTrue(payment.can_release_hold())

        # Create payment with future hold date
        payment_future = Payment.objects.create(
            payment_intent_id="pi_test456",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("50.00"),
            application_fee=Decimal("2.50"),
            status="succeeded",
            hold_until=timezone.now() + timedelta(days=15),  # Future date
        )

        # Should not be eligible for release
        self.assertFalse(payment_future.can_release_hold())

    def test_payment_hold_release_process(self):
        """Test the complete hold release process"""
        # Create payment eligible for release
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            application_fee=Decimal("5.00"),
            status="succeeded",
            hold_until=timezone.now() - timedelta(days=1),
        )

        # Release the hold
        self.assertTrue(payment.release_hold())

        # Check hold was released
        payment.refresh_from_db()
        self.assertFalse(payment.is_held)
        self.assertIsNotNone(payment.hold_released_at)

        # Check seller payouts were created
        self.assertTrue(payment.seller_payouts.exists())
        payout = payment.seller_payouts.first()
        self.assertEqual(payout.seller, self.seller)
        self.assertEqual(payout.stripe_account, self.stripe_account)

    def test_seller_payout_creation(self):
        """Test seller payout creation with proper fee calculation"""
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            application_fee=Decimal("5.00"),
            status="succeeded",
        )

        # Manually create seller payouts to test calculation
        payment.create_seller_payouts()

        payout = SellerPayout.objects.filter(payment=payment).first()
        self.assertIsNotNone(payout)
        self.assertEqual(payout.seller, self.seller)
        self.assertEqual(payout.order_item, self.order_item)

        # Check amount calculation (item price - proportional fee)
        expected_net = Decimal("94.99")  # 99.99 - 5.00
        self.assertEqual(payout.amount, expected_net)
        self.assertEqual(payout.application_fee, Decimal("5.00"))

    def test_refund_request_creation(self):
        """Test refund request creation and validation"""
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            application_fee=Decimal("5.00"),
            status="succeeded",
        )

        refund_request = RefundRequest.objects.create(
            payment=payment,
            order=self.order,
            requested_by=self.buyer,
            amount=Decimal("99.99"),
            reason="defective",
            description="Product was damaged",
        )

        self.assertEqual(refund_request.payment, payment)
        self.assertEqual(refund_request.requested_by, self.buyer)
        self.assertEqual(refund_request.status, "pending")
        self.assertIsNotNone(refund_request.refund_number)
        self.assertTrue(refund_request.refund_number.startswith("REF"))

    def test_refund_approval_process(self):
        """Test refund approval workflow"""
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            status="succeeded",
        )

        refund_request = RefundRequest.objects.create(
            payment=payment,
            order=self.order,
            requested_by=self.buyer,
            amount=Decimal("99.99"),
            reason="defective",
            description="Product was damaged",
        )

        # Create admin user for approval
        admin_user = User.objects.create_user(username="admin", email="admin@test.com", is_staff=True)

        # Approve the refund
        self.assertTrue(refund_request.approve_refund(admin_user))

        refund_request.refresh_from_db()
        self.assertEqual(refund_request.status, "approved")
        self.assertEqual(refund_request.approved_by, admin_user)
        self.assertIsNotNone(refund_request.approved_at)

    def test_webhook_event_logging(self):
        """Test webhook event creation and tracking"""
        webhook_event = WebhookEvent.objects.create(
            stripe_event_id="evt_test123", event_type="payment_intent.succeeded", event_data={"test": "data"}
        )

        self.assertEqual(webhook_event.stripe_event_id, "evt_test123")
        self.assertEqual(webhook_event.event_type, "payment_intent.succeeded")
        self.assertEqual(webhook_event.status, "received")
        self.assertEqual(webhook_event.processing_attempts, 0)

    def test_payment_transaction_logging(self):
        """Test payment transaction logging"""
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            status="succeeded",
        )

        transaction = PaymentTransaction.objects.create(
            stripe_transaction_id="txn_test123",
            payment=payment,
            transaction_type="charge",
            amount=Decimal("99.99"),
            description="Order payment",
            processed_at=timezone.now(),
        )

        self.assertEqual(transaction.payment, payment)
        self.assertEqual(transaction.transaction_type, "charge")
        self.assertEqual(str(transaction), "Charge $99.99")

    def test_payment_validation(self):
        """Test payment model field validation"""
        # Test negative amount should be allowed (for refunds)
        with self.assertRaises(Exception):  # noqa: B017
            payment = Payment(
                payment_intent_id="",  # Empty payment intent ID
                order=self.order,
                buyer=self.buyer,
                amount=Decimal("99.99"),
                status="succeeded",
            )
            payment.full_clean()  # This should raise validation error

    def test_seller_payout_processing(self):
        """Test seller payout processing functionality"""
        payment = Payment.objects.create(
            payment_intent_id="pi_test123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            application_fee=Decimal("5.00"),
            status="succeeded",
        )

        payout = SellerPayout.objects.create(
            payment=payment,
            seller=self.seller,
            stripe_account=self.stripe_account,
            amount=Decimal("94.99"),
            application_fee=Decimal("5.00"),
            order_item=self.order_item,
        )

        self.assertEqual(payout.status, "pending")
        self.assertEqual(str(payout), f"Payout $94.99 to {self.seller.username}")


class PaymentSecurityTestCase(TestCase):
    """Test security features of payment models"""

    def setUp(self):
        self.buyer = User.objects.create_user(username="testbuyer", email="buyer@test.com")
        self.order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("99.99"),
            total_amount=Decimal("99.99"),
            shipping_address={
                "street": "123 Test St",
                "city": "Test City",
                "state": "TC",
                "postal_code": "12345",
                "country": "US",
            },
        )

    def test_payment_intent_id_uniqueness(self):
        """Test that payment intent IDs must be unique"""
        Payment.objects.create(
            payment_intent_id="pi_unique123",
            order=self.order,
            buyer=self.buyer,
            amount=Decimal("99.99"),
            status="succeeded",
        )

        # Should raise IntegrityError for duplicate payment_intent_id
        with self.assertRaises(Exception):  # noqa: B017
            Payment.objects.create(
                payment_intent_id="pi_unique123",  # Duplicate
                order=self.order,
                buyer=self.buyer,
                amount=Decimal("50.00"),
                status="pending",
            )

    def test_stripe_account_id_uniqueness(self):
        """Test that Stripe account IDs must be unique"""
        user1 = User.objects.create_user(username="user1", email="user1@test.com")
        user2 = User.objects.create_user(username="user2", email="user2@test.com")

        StripeAccount.objects.create(user=user1, stripe_account_id="acct_unique123", email=user1.email, country="US")

        # Should raise IntegrityError for duplicate stripe_account_id
        with self.assertRaises(Exception):  # noqa: B017
            StripeAccount.objects.create(
                user=user2,
                stripe_account_id="acct_unique123",
                email=user2.email,
                country="US",  # Duplicate
            )


if __name__ == "__main__":
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    if not settings.configured:
        import os

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "designiaBackend.settings")
        django.setup()

    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["payment_system.testing.test_models"])
    if failures:
        exit(1)
