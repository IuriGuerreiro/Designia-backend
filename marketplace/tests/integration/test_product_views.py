from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import Category, Product

User = get_user_model()


@override_settings(FEATURE_FLAGS={"USE_SERVICE_LAYER_PRODUCTS": True})
class ProductViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users
        self.seller_user = User.objects.create_user(
            username="seller", password="password", email="seller@example.com", role="seller"
        )
        self.buyer_user = User.objects.create_user(
            username="buyer", password="password", email="buyer@example.com", role="user"
        )

        # Create category
        self.category = Category.objects.create(name="Electronics", slug="electronics")

        # Create product
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            description="Description",
            price=100.00,
            seller=self.seller_user,
            category=self.category,
            stock_quantity=10,
            is_active=True,
        )
        # Using the router names from urls.py with app namespace
        self.product_url = reverse("marketplace:product-detail", kwargs={"slug": self.product.slug})
        self.product_list_url = reverse("marketplace:product-list")

    def test_create_product_via_service(self):
        self.client.force_authenticate(user=self.seller_user)
        data = {
            "name": "New Product",
            "description": "New Description",
            "price": "50.00",
            "category_id": self.category.id,
            "stock_quantity": 5,
            "condition": "new",
        }
        response = self.client.post(self.product_list_url, data)
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Create failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 2)
        self.assertTrue(Product.objects.filter(name="New Product").exists())

    def test_update_product_via_service(self):
        self.client.force_authenticate(user=self.seller_user)
        data = {"name": "Updated Name", "price": "150.00"}
        response = self.client.patch(self.product_url, data)
        if response.status_code != status.HTTP_200_OK:
            print(f"Update failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Updated Name")
        self.assertEqual(self.product.price, 150.00)

    def test_delete_product_via_service(self):
        self.client.force_authenticate(user=self.seller_user)
        response = self.client.delete(self.product_url)
        if response.status_code != status.HTTP_204_NO_CONTENT:
            print(f"Delete failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)  # Soft delete

    def test_non_owner_cannot_update(self):
        self.client.force_authenticate(user=self.buyer_user)
        data = {"name": "Hacked Name"}
        response = self.client.patch(self.product_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_delete(self):
        self.client.force_authenticate(user=self.buyer_user)
        response = self.client.delete(self.product_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
