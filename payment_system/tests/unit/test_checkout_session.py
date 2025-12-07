import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework.test import force_authenticate

from marketplace.tests.factories import CartFactory, CartItemFactory, ProductFactory, UserFactory
from payment_system.views import create_checkout_session

User = get_user_model()


class CreateCheckoutSessionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = UserFactory()
        self.cart = CartFactory(user=self.user)
        self.product = ProductFactory(price=Decimal("100.00"), stock_quantity=10)
        self.url = "/api/payments/create-checkout-session/"

    def test_empty_cart(self):
        request = self.factory.post(self.url)
        force_authenticate(request, user=self.user)

        # Mock Cart.items.all() to return empty
        # We rely on actual DB since it's an integration/unit hybrid
        self.cart.items.all().delete()

        response = create_checkout_session(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("EMPTY_CART", str(response.data))

    def test_insufficient_stock(self):
        CartItemFactory(cart=self.cart, product=self.product, quantity=11)

        request = self.factory.post(self.url)
        force_authenticate(request, user=self.user)

        response = create_checkout_session(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("INSUFFICIENT_STOCK", str(response.data))

    def test_invalid_price(self):
        self.product.price = Decimal("0.00")
        self.product.save()
        CartItemFactory(cart=self.cart, product=self.product, quantity=1)

        request = self.factory.post(self.url)
        force_authenticate(request, user=self.user)

        response = create_checkout_session(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("INVALID_PRICE", str(response.data))

    def test_invalid_quantity(self):
        item = CartItemFactory(cart=self.cart, product=self.product, quantity=0)

        # Since I can't easily force invalid quantity via factory if validation prevents it,
        # I'll try to set it directly.
        item.quantity = 0
        item.save()

        request = self.factory.post(self.url)
        force_authenticate(request, user=self.user)

        response = create_checkout_session(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("INVALID_QUANTITY", str(response.data))

    @patch("payment_system.views.stripe.checkout.Session.create")
    def test_create_session_success(self, mock_stripe_create):
        CartItemFactory(cart=self.cart, product=self.product, quantity=1)

        mock_stripe_create.return_value = MagicMock(client_secret="cs_secret_123", id="cs_123")

        request = self.factory.post(self.url)
        force_authenticate(request, user=self.user)

        response = create_checkout_session(request)
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        self.assertIn("clientSecret", content)

        # Verify stock reservation
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 9)  # 10 - 1
