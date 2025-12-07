from decimal import Decimal  # Import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import Product
from marketplace.tests.factories import (
    CategoryFactory,
    ProductARModelFactory,
    ProductFactory,
    ProductReviewFactory,
    SellerFactory,
    UserFactory,
)

User = get_user_model()


@override_settings(FEATURE_FLAGS={"USE_SERVICE_LAYER_PRODUCTS": True})
class ProductViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users and categories using factories
        self.seller_user = SellerFactory()
        self.buyer_user = UserFactory()
        self.category = CategoryFactory()

        # Create products using factories
        self.product_regular = ProductFactory(seller=self.seller_user, category=self.category, stock_quantity=10)
        self.product_on_sale = ProductFactory(
            seller=self.seller_user,
            category=self.category,
            price=self.product_regular.price - Decimal("10.00"),
            original_price=self.product_regular.price,
            stock_quantity=5,
        )
        self.product_out_of_stock = ProductFactory(seller=self.seller_user, category=self.category, stock_quantity=0)

        # Product with AR model
        self.product_with_ar = ProductFactory(
            seller=self.seller_user, category=self.category, name="AR Product", slug="ar-product"
        )
        ProductARModelFactory(product=self.product_with_ar)  # Create an AR model for it

        # Add a review for one of the products
        ProductReviewFactory(product=self.product_regular, reviewer=self.buyer_user, rating=4)
        ProductReviewFactory(product=self.product_regular, reviewer=UserFactory(email="another@example.com"), rating=5)

        # Using the router names from urls.py with app namespace
        self.product_regular_url = reverse("marketplace:product-detail", kwargs={"slug": self.product_regular.slug})
        self.product_on_sale_url = reverse("marketplace:product-detail", kwargs={"slug": self.product_on_sale.slug})
        self.product_with_ar_url = reverse("marketplace:product-detail", kwargs={"slug": self.product_with_ar.slug})
        self.product_list_url = reverse("marketplace:product-list")

    def test_list_products_returns_service_data(self):
        response = self.client.get(self.product_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle paginated and non-paginated responses
        products_data = (
            response.data.get("results")
            if isinstance(response.data, dict) and "results" in response.data
            else response.data
        )
        self.assertIsInstance(products_data, list)
        self.assertGreater(len(products_data), 0)

        # Find product_regular in the list response
        product_data = next((item for item in products_data if item["id"] == str(self.product_regular.id)), None)
        self.assertIsNotNone(product_data)
        self.assertFalse(product_data["is_on_sale"])
        # Average rating should be (4+5)/2 = 4.5
        self.assertEqual(Decimal(str(product_data["average_rating"])), Decimal("4.50"))
        self.assertEqual(product_data["review_count"], 2)
        self.assertTrue(product_data["is_in_stock"])

        # Find product_on_sale in the list response
        product_data_sale = next((item for item in products_data if item["id"] == str(self.product_on_sale.id)), None)
        self.assertIsNotNone(product_data_sale)
        self.assertTrue(product_data_sale["is_on_sale"])
        self.assertGreater(product_data_sale["discount_percentage"], 0)
        self.assertTrue(product_data_sale["is_in_stock"])

    def test_retrieve_product_detail_returns_service_data(self):
        response = self.client.get(self.product_regular_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product_data = response.data

        self.assertFalse(product_data["is_on_sale"])
        self.assertEqual(Decimal(str(product_data["average_rating"])), Decimal("4.50"))
        self.assertEqual(product_data["review_count"], 2)
        self.assertTrue(product_data["is_in_stock"])
        self.assertFalse(product_data["has_ar_model"])  # regular product does not have AR model

        response_ar = self.client.get(self.product_with_ar_url)
        self.assertEqual(response_ar.status_code, status.HTTP_200_OK)
        product_ar_data = response_ar.data
        self.assertTrue(product_ar_data["has_ar_model"])

    def test_create_product_via_service(self):
        self.client.force_authenticate(user=self.seller_user)
        data = {
            "name": "New Product",
            "description": "New Description",
            "price": "50.00",
            "category": self.category.id,
            "stock_quantity": 5,
            "condition": "new",
        }
        response = self.client.post(self.product_list_url, data)
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Create failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 5)  # 4 from setup + 1 new
        self.assertTrue(Product.objects.filter(name="New Product").exists())

    def test_update_product_via_service(self):
        self.client.force_authenticate(user=self.seller_user)
        data = {"name": "Updated Name", "price": "150.00"}
        response = self.client.patch(self.product_regular_url, data)
        if response.status_code != status.HTTP_200_OK:
            print(f"Update failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product_regular.refresh_from_db()
        self.assertEqual(self.product_regular.name, "Updated Name")
        self.assertEqual(self.product_regular.price, Decimal("150.00"))

    def test_delete_product_via_service(self):
        self.client.force_authenticate(user=self.seller_user)
        response = self.client.delete(self.product_regular_url)
        if response.status_code != status.HTTP_204_NO_CONTENT:
            print(f"Delete failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.product_regular.refresh_from_db()
        self.assertFalse(self.product_regular.is_active)  # Soft delete

    def test_non_owner_cannot_update(self):
        self.client.force_authenticate(user=self.buyer_user)
        data = {"name": "Hacked Name"}
        response = self.client.patch(self.product_regular_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_owner_cannot_delete(self):
        self.client.force_authenticate(user=self.buyer_user)
        response = self.client.delete(self.product_regular_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
