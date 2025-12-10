# Designia-backend/marketplace/tests/integration/test_cart_views.py
import uuid  # Import uuid for explicit ID generation
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import CartItem
from marketplace.tests.factories import CategoryFactory, ProductFactory, SellerFactory, UserFactory

User = get_user_model()


@override_settings(TAX_RATES={"default": Decimal("0")})
class CartViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users using factories with explicit UUIDs
        self.user1 = UserFactory(username="user1", email="user1@example.com")
        self.user2 = UserFactory(username="user2", email="user2@example.com")
        self.seller1 = SellerFactory(username="seller1", email="seller1@example.com")
        self.seller2 = SellerFactory(username="seller2", email="seller2@example.com")

        # Create category using factory
        self.category = CategoryFactory()

        # Create products using factories
        self.product1 = ProductFactory(
            seller=self.seller1, category=self.category, stock_quantity=10, price=Decimal("10.00")
        )
        self.product2 = ProductFactory(
            seller=self.seller2, category=self.category, stock_quantity=5, price=Decimal("20.00")
        )

        # URLs for the CartViewSet actions, using app_name and basename
        self.cart_list_url = reverse("marketplace:cart-list")
        self.cart_add_item_url = reverse("marketplace:cart-add-item")
        self.cart_update_item_url = reverse("marketplace:cart-update-item")
        self.cart_remove_item_url = reverse("marketplace:cart-remove-item")
        self.cart_clear_url = reverse("marketplace:cart-clear")
        self.cart_status_url = reverse("marketplace:cart-status")
        self.cart_validate_stock_url = reverse("marketplace:cart-validate-stock")

    def test_list_empty_cart(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.cart_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items_count"], 0)
        self.assertEqual(Decimal(response.data["totals"]["total"]), Decimal("0.00"))

    def test_add_item_to_cart(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # Service returns full cart data
        self.assertEqual(response.data["items_count"], 1)
        self.assertEqual(response.data["items"][0]["product"]["id"], str(self.product1.id))
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(Decimal(response.data["totals"]["total"]), Decimal("20.00"))

    def test_add_item_insufficient_stock(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(self.cart_add_item_url, {"product_id": str(self.product2.id), "quantity": 100})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient stock", response.data["detail"])

    def test_add_item_product_not_found(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(self.cart_add_item_url, {"product_id": str(uuid.uuid4()), "quantity": 1})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("not found", response.data["detail"])

    def test_update_item_quantity(self):
        self.client.force_authenticate(user=self.user1)
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})

        response = self.client.patch(self.cart_update_item_url, {"product_id": str(self.product1.id), "quantity": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items_count"], 1)
        self.assertEqual(response.data["items"][0]["quantity"], 5)
        self.assertEqual(Decimal(response.data["totals"]["total"]), Decimal("50.00"))

    def test_update_item_invalid_quantity(self):
        self.client.force_authenticate(user=self.user1)
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})

        response = self.client.patch(self.cart_update_item_url, {"product_id": str(self.product1.id), "quantity": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Quantity must be positive", response.data["detail"])

    def test_remove_item_from_cart(self):
        self.client.force_authenticate(user=self.user1)
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})
        self.assertEqual(CartItem.objects.count(), 1)

        response = self.client.delete(self.cart_remove_item_url, {"product_id": str(self.product1.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(response.data["items_count"], 0)

    def test_clear_cart(self):
        self.client.force_authenticate(user=self.user1)
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product2.id), "quantity": 1})
        self.assertEqual(CartItem.objects.count(), 2)

        response = self.client.delete(self.cart_clear_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_get_cart_status(self):
        self.client.force_authenticate(user=self.user1)
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})

        response = self.client.get(self.cart_status_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("20.00"))

    def test_validate_stock(self):
        self.client.force_authenticate(user=self.user1)
        self.client.post(self.cart_add_item_url, {"product_id": str(self.product1.id), "quantity": 2})

        response = self.client.post(self.cart_validate_stock_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["items"][0]["product_id"], str(self.product1.id))
        self.assertEqual(response.data["total_items"], 1)

        # Make product out of stock
        self.product1.stock_quantity = 1
        self.product1.save()

        response = self.client.post(self.cart_validate_stock_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["valid"])
        self.assertEqual(response.data["items"][0]["product_id"], str(self.product1.id))
        self.assertEqual(response.data["items"][0]["issues"][0], "Insufficient stock. Requested: 2, available 1")
