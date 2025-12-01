from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import Cart, CartItem, Category, Order, OrderItem, Product

User = get_user_model()


@override_settings(TAX_RATES={"default": Decimal("0.00")}, SHIPPING_FLAT_RATE=Decimal("0.00"))
class OrderViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users
        self.buyer = User.objects.create_user(username="buyer", password="password", email="buyer@example.com")
        self.seller1 = User.objects.create_user(
            username="seller1", password="password", email="seller1@example.com", role="seller"
        )
        self.seller2 = User.objects.create_user(
            username="seller2", password="password", email="seller2@example.com", role="seller"
        )
        self.admin_user = User.objects.create_user(
            username="admin", password="password", email="admin@example.com", role="admin", is_staff=True
        )

        # Create category
        self.category = Category.objects.create(name="Electronics", slug="electronics")

        # Create products
        self.product1 = Product.objects.create(
            name="Product 1",
            slug="product-1",
            description="Desc 1",
            price=10.00,
            seller=self.seller1,
            category=self.category,
            stock_quantity=10,
            is_active=True,
        )
        self.product2 = Product.objects.create(
            name="Product 2",
            slug="product-2",
            description="Desc 2",
            price=20.00,
            seller=self.seller2,
            category=self.category,
            stock_quantity=5,
            is_active=True,
        )

        # Create cart for buyer
        self.cart = Cart.objects.create(user=self.buyer)
        CartItem.objects.create(cart=self.cart, product=self.product1, quantity=2)
        CartItem.objects.create(cart=self.cart, product=self.product2, quantity=1)  # Total: 20 + 20 = 40

        self.order_list_url = reverse("marketplace:order-list")
        self.order_create_url = reverse("marketplace:order-list")  # create uses list URL

    def test_create_order_success(self):
        self.client.force_authenticate(user=self.buyer)
        shipping_address = {
            "street": "123 Main St",
            "city": "Test City",
            "country": "Test Country",
            "postal_code": "12345",
        }
        response = self.client.post(
            self.order_create_url,
            {"shipping_address": shipping_address, "buyer_notes": "Please deliver fast"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 2)
        self.assertEqual(response.data["total_amount"], "40.00")

        # Verify cart is cleared
        cart_items = CartItem.objects.filter(cart=self.cart).count()
        self.assertEqual(cart_items, 0)

        # Verify stock reduced
        self.product1.refresh_from_db()
        self.product2.refresh_from_db()
        self.assertEqual(self.product1.stock_quantity, 8)
        self.assertEqual(self.product2.stock_quantity, 4)

    def test_create_order_empty_cart(self):
        # Clear cart before test
        CartItem.objects.filter(cart=self.cart).delete()
        self.client.force_authenticate(user=self.buyer)
        shipping_address = {
            "street": "123 Main St",
            "city": "Test City",
            "country": "Test Country",
            "postal_code": "12345",
        }
        response = self.client.post(self.order_create_url, {"shipping_address": shipping_address}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("empty cart", response.data["detail"])

    def test_create_order_insufficient_stock(self):
        self.product1.stock_quantity = 1
        self.product1.save()  # Cart wants 2

        self.client.force_authenticate(user=self.buyer)
        shipping_address = {
            "street": "123 Main St",
            "city": "Test City",
            "country": "Test Country",
            "postal_code": "12345",
        }
        response = self.client.post(self.order_create_url, {"shipping_address": shipping_address}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cart validation failed", response.data["detail"])

    def test_list_orders_success(self):
        self.client.force_authenticate(user=self.buyer)

        # Create a test order
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        response = self.client.get(self.order_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(order.id))

    def test_list_orders_other_user_fail(self):
        other_buyer = User.objects.create_user(
            username="other_buyer", password="password", email="other_buyer@example.com"
        )
        Order.objects.create(
            buyer=other_buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        self.client.force_authenticate(user=self.buyer)
        response = self.client.get(self.order_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)  # Should not see other user's order

    def test_retrieve_order_success(self):
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        self.client.force_authenticate(user=self.buyer)
        url = reverse("marketplace:order-detail", args=[order.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(order.id))
        self.assertEqual(len(response.data["items"]), 1)

    def test_retrieve_order_other_user_fail(self):
        other_buyer = User.objects.create_user(
            username="other_buyer", password="password", email="other_buyer@example.com"
        )
        order = Order.objects.create(
            buyer=other_buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        self.client.force_authenticate(user=self.buyer)
        url = reverse("marketplace:order-detail", args=[order.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # Not owner

    def test_update_shipping_success(self):
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        self.client.force_authenticate(user=self.seller1)  # Seller of product1
        url = reverse("marketplace:order-update-shipping", args=[order.id])
        data = {"tracking_number": "TRK123", "shipping_carrier": "FedEx"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "shipped")
        self.assertEqual(order.tracking_number, "TRK123")

    def test_update_shipping_permission_denied(self):
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        self.client.force_authenticate(user=self.buyer)  # Buyer
        url = reverse("marketplace:order-update-shipping", args=[order.id])
        data = {"tracking_number": "TRK123", "shipping_carrier": "FedEx"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_order_success(self):
        # Create an order that can be cancelled
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        # Manually decrement stock to simulate reservation since we are creating order directly
        # and then call the service which expects a previous reservation
        self.product1.stock_quantity -= 1
        self.product1.save()
        self.assertEqual(self.product1.stock_quantity, 9)  # Verify stock is now 9

        self.client.force_authenticate(user=self.buyer)
        url = reverse("marketplace:order-cancel", args=[order.id])
        data = {"reason": "Changed my mind"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.cancellation_reason, "Changed my mind")

        # Verify stock released
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock_quantity, 10)  # Original stock

    def test_cancel_order_permission_denied(self):
        other_buyer = User.objects.create_user(
            username="other_buyer", password="password", email="other_buyer@example.com"
        )
        order = Order.objects.create(
            buyer=other_buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="payment_confirmed",
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        self.client.force_authenticate(user=self.buyer)  # Not owner
        url = reverse("marketplace:order-cancel", args=[order.id])
        data = {"reason": "Not my order"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_order_already_shipped(self):
        order = Order.objects.create(
            buyer=self.buyer,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("12.00"),
            shipping_address={"street": "1", "city": "2", "country": "3"},
            status="shipped",  # Already shipped
        )
        OrderItem.objects.create(order=order, product=self.product1, seller=self.seller1, quantity=1, unit_price=10.00)

        self.client.force_authenticate(user=self.buyer)
        url = reverse("marketplace:order-cancel", args=[order.id])
        data = {"reason": "Too late"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot cancel order in status 'shipped'", response.data["detail"])
