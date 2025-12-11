"""
Comprehensive Test Suite for Payment System
Tests all endpoints with authentication, permissions, error handling, and edge cases
"""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from marketplace.models import Cart, CartItem, Category, Order, OrderItem, Product
from payment_system.models import PaymentTransaction, Payout, PayoutItem


User = get_user_model()


class TestDataFactory:
    """Factory for creating test data"""

    @staticmethod
    def create_user(username, email, password="testpass123", role="user"):
        """Create a test user with specified role"""
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=f"Test{username}",
            last_name="User",
            role=role,
        )
        return user

    @staticmethod
    def create_admin():
        """Create an admin user"""
        return TestDataFactory.create_user("admin", "admin@test.com", role="admin")

    @staticmethod
    def create_seller(username="testseller"):
        """Create a seller user"""
        return TestDataFactory.create_user(username, f"{username}@test.com", role="seller")

    @staticmethod
    def create_buyer(username="testbuyer"):
        """Create a buyer user"""
        return TestDataFactory.create_user(username, f"{username}@test.com", role="user")

    @staticmethod
    def create_product(seller, name="Test Product", price="99.99"):
        """Create a test product"""
        category = Category.objects.first()
        if not category:
            category = Category.objects.create(name="Test Category", slug="test-category")

        product = Product.objects.create(
            name=name,
            slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}",
            description=f"Description for {name}",
            price=Decimal(price),
            seller=seller,
            category=category,
            stock_quantity=10,
        )
        return product

    @staticmethod
    def create_order(buyer, seller, product, status="pending"):
        """Create a test order"""
        order = Order.objects.create(
            buyer=buyer,
            subtotal=product.price,
            total_amount=product.price,
            shipping_address={
                "street": "123 Test St",
                "city": "Test City",
                "state": "TC",
                "postal_code": "12345",
                "country": "US",
            },
            status=status,
        )

        OrderItem.objects.create(
            order=order,
            product=product,
            seller=seller,
            quantity=1,
            unit_price=product.price,
            total_price=product.price,
            product_name=product.name,
            product_description=product.description,
        )

        return order

    @staticmethod
    def create_payment_transaction(seller, buyer, order, status="held"):
        """Create a test payment transaction"""
        transaction = PaymentTransaction.objects.create(
            seller=seller,
            buyer=buyer,
            order=order,
            stripe_payment_intent_id=f"pi_test_{uuid4().hex[:12]}",
            gross_amount=Decimal("99.99"),
            platform_fee=Decimal("4.99"),
            stripe_fee=Decimal("3.17"),
            net_amount=Decimal("91.83"),
            currency="usd",
            status=status,
            hold_reason="first_sale",
            days_to_hold=7,
            hold_start_date=timezone.now(),
            planned_release_date=timezone.now() + timedelta(days=7),
        )
        return transaction

    @staticmethod
    def create_payout(seller, amount="100.00", status="pending"):
        """Create a test payout"""
        amount_decimal = Decimal(amount)
        amount_cents = int(amount_decimal * 100)
        payout = Payout.objects.create(
            seller=seller,
            stripe_payout_id=f"po_test_{uuid4().hex[:12]}",
            amount_decimal=amount_decimal,
            amount_cents=amount_cents,
            currency="usd",
            status=status,
            payout_type="standard",
        )
        return payout


class BaseAuthTestCase(APITestCase):
    """Base test case with authentication helpers"""

    def setUp(self):
        """Set up test data"""
        self.factory = TestDataFactory()
        self.client = APIClient()

        # Create test users
        self.buyer = self.factory.create_buyer()
        self.seller = self.factory.create_seller()
        self.seller2 = self.factory.create_seller("testseller2")
        self.admin = self.factory.create_admin()
        self.regular_user = self.factory.create_user("regularuser", "regular@test.com")

        # Enable 2FA for sellers (required for Stripe operations)
        self.seller.two_factor_enabled = True
        self.seller.stripe_account_id = "acct_test_seller1"
        self.seller.save()
        self.seller2.two_factor_enabled = True
        self.seller2.stripe_account_id = "acct_test_seller2"
        self.seller2.save()

        # Generate tokens
        self.buyer_token = str(RefreshToken.for_user(self.buyer).access_token)
        self.seller_token = str(RefreshToken.for_user(self.seller).access_token)
        self.seller2_token = str(RefreshToken.for_user(self.seller2).access_token)
        self.admin_token = str(RefreshToken.for_user(self.admin).access_token)
        self.regular_token = str(RefreshToken.for_user(self.regular_user).access_token)

    def authenticate(self, user):
        """Force authenticate as given user (bypass JWT)"""
        self.client.force_authenticate(user=user)

    def authenticate_buyer(self):
        self.authenticate(self.buyer)

    def authenticate_seller(self):
        self.authenticate(self.seller)

    def authenticate_seller2(self):
        self.authenticate(self.seller2)

    def authenticate_admin(self):
        self.authenticate(self.admin)

    def authenticate_regular(self):
        self.authenticate(self.regular_user)

    def unauthenticate(self):
        """Remove authentication"""
        self.client.force_authenticate(user=None)


class CheckoutEndpointTests(BaseAuthTestCase):
    """Test checkout session creation endpoints"""

    def setUp(self):
        super().setUp()
        self.product = self.factory.create_product(self.seller)
        # Create cart and add items for buyer (for regular checkout)
        self.cart = Cart.get_or_create_cart(user=self.buyer)
        self.cart_item = CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        # Create order with pending_payment status (for retry checkout)
        self.order = self.factory.create_order(self.buyer, self.seller, self.product)
        self.order.status = "pending_payment"
        self.order.save()

    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session_success(self, mock_stripe):
        """Test successful checkout session creation"""
        mock_stripe.return_value = Mock(
            id="cs_test123",
            client_secret="test_secret",
            url="https://checkout.stripe.com/test",
            payment_status="unpaid",
        )

        self.authenticate_buyer()
        url = reverse("payment_system:create_checkout_session")

        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # JsonResponse returns JSON content, parse it

        response_data = json.loads(response.content)
        self.assertIn("clientSecret", response_data)

    def test_create_checkout_session_unauthenticated(self):
        """Test checkout requires authentication"""
        self.unauthenticate()
        url = reverse("payment_system:create_checkout_session")

        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("stripe.checkout.Session.create")
    def test_retry_checkout_session(self, mock_stripe):
        """Test retry checkout for failed order"""
        mock_stripe.return_value = Mock(
            id="cs_test_retry123",
            client_secret="test_secret_retry",
            url="https://checkout.stripe.com/test-retry",
            payment_status="unpaid",
        )

        self.authenticate_buyer()
        url = reverse("payment_system:create_retry_checkout_session", kwargs={"order_id": self.order.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class StripeConnectEndpointTests(BaseAuthTestCase):
    """Test Stripe Connect account management endpoints"""

    @patch("stripe.Account.create")
    def test_create_stripe_account_success(self, mock_stripe):
        """Test Stripe account creation"""
        mock_stripe.return_value = Mock(id="acct_test123", charges_enabled=False, details_submitted=False)

        self.authenticate_seller()
        # Remove existing stripe_account_id to test actual account creation
        self.seller.stripe_account_id = None
        self.seller.save()

        url = reverse("payment_system:stripe_account")
        data = {"country": "US", "business_type": "individual"}

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_stripe_account_non_seller(self):
        """Test non-seller gets validation error (no seller role check in code currently)"""
        self.authenticate_regular()
        url = reverse("payment_system:stripe_account")
        data = {"country": "US"}

        response = self.client.post(url, data, format="json")
        # Currently returns 400 for validation failures (2FA not enabled)
        # If seller role checking is added, this should be 403
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("payment_system.views.stripe.AccountSession.create")
    def test_create_account_session(self, mock_stripe):
        """Test Stripe account session creation"""
        mock_stripe.return_value = Mock(client_secret="test_session_secret")

        self.authenticate_seller()
        url = reverse("payment_system:create_stripe_account_session")

        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_account_status_unauthenticated(self):
        """Test account status requires authentication"""
        self.unauthenticate()
        url = reverse("payment_system:get_stripe_account_status")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PaymentHoldsEndpointTests(BaseAuthTestCase):
    """Test payment holds endpoints"""

    def setUp(self):
        super().setUp()
        self.product = self.factory.create_product(self.seller)
        self.order = self.factory.create_order(self.buyer, self.seller, self.product, status="completed")
        self.transaction = self.factory.create_payment_transaction(self.seller, self.buyer, self.order, status="held")

    def test_get_seller_payment_holds_success(self):
        """Test seller can view their payment holds"""
        self.authenticate_seller()
        url = reverse("payment_system:get_seller_payment_holds")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("holds", response.data)
        self.assertIn("summary", response.data)

    def test_get_payment_holds_admin_access(self):
        """Test admin can view payment holds"""
        self.authenticate_admin()
        url = reverse("payment_system:get_seller_payment_holds")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_payment_holds_non_seller(self):
        """Test non-seller cannot view payment holds"""
        self.authenticate_regular()
        url = reverse("payment_system:get_seller_payment_holds")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_payment_holds_unauthenticated(self):
        """Test unauthenticated access is denied"""
        self.unauthenticate()
        url = reverse("payment_system:get_seller_payment_holds")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PayoutEndpointTests(BaseAuthTestCase):
    """Test payout creation and management endpoints"""

    def setUp(self):
        super().setUp()
        self.product = self.factory.create_product(self.seller)
        self.order = self.factory.create_order(self.buyer, self.seller, self.product, status="completed")
        self.transaction = self.factory.create_payment_transaction(
            self.seller, self.buyer, self.order, status="released"
        )

    def test_create_payout_disabled_for_seller(self):
        """Seller receives disabled response when attempting manual payout creation"""
        self.authenticate_seller()
        url = reverse("payment_system:seller_payout")
        response = self.client.post(url, {"amount": 9000, "currency": "usd"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertEqual(response.data.get("error"), "PAYOUT_CREATION_DISABLED")

    def test_create_payout_disabled_for_admin(self):
        """Admin users also receive disabled response"""
        self.authenticate_admin()
        url = reverse("payment_system:seller_payout")
        response = self.client.post(url, {"amount": 5000, "currency": "usd"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertEqual(response.data.get("error"), "PAYOUT_CREATION_DISABLED")

    def test_create_payout_disabled_for_non_seller(self):
        """Non-sellers receive the same disabled response"""
        self.authenticate_regular()
        url = reverse("payment_system:seller_payout")
        response = self.client.post(url, {"amount": 5000, "currency": "usd"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertEqual(response.data.get("error"), "PAYOUT_CREATION_DISABLED")

    def test_user_payouts_list_success(self):
        """Test seller can list their payouts"""
        _payout = self.factory.create_payout(self.seller)

        self.authenticate_seller()
        url = reverse("payment_system:user_payouts_list")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("payouts", response.data)

    def test_user_payouts_list_admin_access(self):
        """Test admin can list payouts"""
        self.authenticate_admin()
        url = reverse("payment_system:user_payouts_list")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payout_detail_success(self):
        """Test seller can view payout details"""
        payout = self.factory.create_payout(self.seller)

        self.authenticate_seller()
        url = reverse("payment_system:payout_detail", kwargs={"payout_id": payout.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_payout_detail_wrong_seller(self):
        """Test seller cannot view another seller's payout"""
        payout = self.factory.create_payout(self.seller2)

        self.authenticate_seller()
        url = reverse("payment_system:payout_detail", kwargs={"payout_id": payout.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_payout_detail_admin_access(self):
        """Test admin cannot view seller's payout via seller endpoint (use admin endpoints instead)"""
        payout = self.factory.create_payout(self.seller)

        self.authenticate_admin()
        url = reverse("payment_system:payout_detail", kwargs={"payout_id": payout.id})

        response = self.client.get(url)
        # Admin should use admin-specific endpoints, not seller endpoints
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_payout_orders_success(self):
        """Test viewing orders in a payout"""
        from django.utils import timezone

        payout = self.factory.create_payout(self.seller)
        PayoutItem.objects.create(
            payout=payout,
            payment_transfer=self.transaction,
            transfer_amount=self.transaction.net_amount,
            transfer_currency="usd",
            transfer_date=timezone.now(),
        )

        self.authenticate_seller()
        url = reverse("payment_system:payout_orders", kwargs={"payout_id": payout.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("orders", response.data)


class AdminPayoutEndpointTests(BaseAuthTestCase):
    """Test admin-only payout oversight endpoints"""

    def setUp(self):
        super().setUp()
        # Create test payouts for multiple sellers
        self.payout1 = self.factory.create_payout(self.seller, "100.00", "pending")
        self.payout2 = self.factory.create_payout(self.seller2, "200.00", "paid")

        # Create transactions for sellers
        product1 = self.factory.create_product(self.seller)
        order1 = self.factory.create_order(self.buyer, self.seller, product1)
        self.transaction1 = self.factory.create_payment_transaction(self.seller, self.buyer, order1, "completed")

        product2 = self.factory.create_product(self.seller2, "Product 2")
        order2 = self.factory.create_order(self.buyer, self.seller2, product2)
        self.transaction2 = self.factory.create_payment_transaction(self.seller2, self.buyer, order2, "held")

    def test_admin_list_all_payouts_success(self):
        """Test admin can list all payouts"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_payouts")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("payouts", response.data)
        self.assertIn("pagination", response.data)
        self.assertIn("summary", response.data)
        self.assertEqual(len(response.data["payouts"]), 2)

    def test_admin_list_payouts_with_filters(self):
        """Test admin can filter payouts"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_payouts")

        # Filter by status
        response = self.client.get(url, {"status": "pending"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["payouts"]), 1)
        self.assertEqual(response.data["payouts"][0]["status"], "pending")

    def test_admin_list_payouts_pagination(self):
        """Test pagination works correctly"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_payouts")

        response = self.client.get(url, {"page_size": 1, "offset": 0})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["payouts"]), 1)
        self.assertTrue(response.data["pagination"]["has_next"])

    def test_admin_list_payouts_non_admin(self):
        """Test non-admin cannot list all payouts"""
        self.authenticate_seller()
        url = reverse("payment_system:admin_list_all_payouts")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("ADMIN_ACCESS_REQUIRED", response.data["error"])

    def test_admin_list_payouts_regular_user(self):
        """Test regular user cannot list all payouts"""
        self.authenticate_regular()
        url = reverse("payment_system:admin_list_all_payouts")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_list_all_transactions_success(self):
        """Test admin can list all transactions"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_transactions")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("transactions", response.data)
        self.assertIn("pagination", response.data)
        self.assertIn("summary", response.data)
        self.assertEqual(len(response.data["transactions"]), 2)

    def test_admin_list_transactions_with_filters(self):
        """Test admin can filter transactions"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_transactions")

        # Filter by status
        response = self.client.get(url, {"status": "held"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["transactions"]), 1)

    def test_admin_list_transactions_search(self):
        """Test admin can search transactions"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_transactions")

        response = self.client.get(url, {"search": self.seller.username})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["transactions"]), 1)

    def test_admin_list_transactions_non_admin(self):
        """Test non-admin cannot list all transactions"""
        self.authenticate_seller()
        url = reverse("payment_system:admin_list_all_transactions")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("ADMIN_ACCESS_REQUIRED", response.data["error"])

    def test_admin_endpoints_unauthenticated(self):
        """Test admin endpoints require authentication"""
        self.unauthenticate()

        payouts_url = reverse("payment_system:admin_list_all_payouts")
        transactions_url = reverse("payment_system:admin_list_all_transactions")

        response1 = self.client.get(payouts_url)
        response2 = self.client.get(transactions_url)

        self.assertEqual(response1.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response2.status_code, status.HTTP_401_UNAUTHORIZED)


class SecurityAndPermissionTests(BaseAuthTestCase):
    """Test security and permission enforcement across all endpoints"""

    def test_role_verification_from_database(self):
        """Test that role is always verified from database, not token"""
        # This tests the core security principle: never trust the token
        self.authenticate_seller()

        # Change role in database
        self.seller.role = "user"
        self.seller.save()

        # Try to access seller endpoint - should fail
        url = reverse("payment_system:get_seller_payment_holds")
        response = self.client.get(url)

        # Should be denied because DB role is now 'user'
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_role_verification(self):
        """Test admin role is verified from database"""
        self.authenticate_admin()

        # Change admin role in database
        self.admin.role = "user"
        self.admin.save()

        # Try to access admin endpoint
        url = reverse("payment_system:admin_list_all_payouts")
        response = self.client.get(url)

        # Should be denied
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_seller_access_prevention(self):
        """Test sellers cannot access other sellers' data"""
        payout = self.factory.create_payout(self.seller2)

        self.authenticate_seller()
        url = reverse("payment_system:payout_detail", kwargs={"payout_id": payout.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_sql_injection_prevention(self):
        """Test SQL injection attempts are handled safely"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_transactions")

        # Attempt SQL injection in search parameter
        malicious_search = "'; DROP TABLE payment_transaction; --"
        response = self.client.get(url, {"search": malicious_search})

        # Should handle safely and return 200 (no results)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify table still exists by making another query
        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)


class EdgeCaseAndErrorHandlingTests(BaseAuthTestCase):
    """Test edge cases and error handling"""

    def test_invalid_uuid_handling(self):
        """Test handling of invalid UUIDs"""
        self.authenticate_seller()

        # Try to access payout with invalid UUID
        invalid_url = "/api/payments/payouts/invalid-uuid-format/"
        response = self.client.get(invalid_url)

        # Should return 404 or 400
        self.assertIn(response.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST])

    def test_large_pagination_offset(self):
        """Test handling of very large pagination offsets"""
        self.authenticate_admin()
        url = reverse("payment_system:admin_list_all_payouts")

        response = self.client.get(url, {"offset": 999999, "page_size": 50})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["payouts"]), 0)

    def test_zero_amount_payout(self):
        """Test handling of zero amount payout"""
        self.authenticate_seller()
        url = reverse("payment_system:seller_payout")
        data = {"amount": 0, "currency": "usd"}

        response = self.client.post(url, data, format="json")
        # Feature disabled -> 410 Gone
        self.assertEqual(response.status_code, status.HTTP_410_GONE)

    def test_negative_amount_payout(self):
        """Test handling of negative amount"""
        self.authenticate_seller()
        url = reverse("payment_system:seller_payout")
        data = {"amount": -5000, "currency": "usd"}

        response = self.client.post(url, data, format="json")
        # Feature disabled -> 410 Gone
        self.assertEqual(response.status_code, status.HTTP_410_GONE)

    def test_concurrent_payout_creation(self):
        """Test handling of concurrent payout creation attempts"""
        # This would require actual concurrent requests
        # Placeholder for integration test
        pass

    def test_malformed_json(self):
        """Test handling of malformed JSON"""
        self.authenticate_seller()
        # Use an enabled endpoint for this generic test
        url = reverse("payment_system:create_stripe_account_session")

        response = self.client.post(
            url,
            data='{"amount": "not-a-number", "currency": }',
            content_type="application/json",  # Invalid JSON
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields(self):
        """Test handling of missing required fields"""
        self.authenticate_seller()
        # Use stripe account creation which requires specific fields
        url = reverse("payment_system:stripe_account")
        data = {"business_type": "individual"}  # Missing country

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


if __name__ == "__main__":
    import os

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    django.setup()

    from django.test.runner import DiscoverRunner

    runner = DiscoverRunner(verbosity=2)
    runner.run_tests(["payment_system.tests.test_all_endpoints"])
