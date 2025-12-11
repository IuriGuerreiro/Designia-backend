# Designia-backend/marketplace/tests/test_catalog_service.py
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from marketplace.models import Category, Product, ProductImage
from marketplace.services import CatalogService, ErrorCodes


User = get_user_model()


class CatalogServiceUnitTest(TestCase):
    def setUp(self):
        # Create users
        self.seller_user = User.objects.create_user(
            username="seller", password="password", email="seller@example.com", role="seller"
        )
        self.buyer_user = User.objects.create_user(
            username="buyer", password="password", email="buyer@example.com", role="user"
        )
        self.admin_user = User.objects.create_user(
            username="admin", password="password", email="admin@example.com", role="admin", is_superuser=True
        )

        # Create category
        self.category = Category.objects.create(name="Electronics", slug="electronics")

        # Create product owned by seller_user
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

        # Mock the storage service for CatalogService
        self.mock_storage = MagicMock()
        self.catalog_service = CatalogService(storage=self.mock_storage)

    @patch("marketplace.catalog.domain.services.catalog_service.is_seller", return_value=True)
    def test_create_product_success(self, mock_is_seller):
        data = {
            "name": "New Product",
            "description": "New Description",
            "price": "50.00",
            "category_id": self.category.id,
            "stock_quantity": 5,
            "condition": "new",
        }
        self.mock_storage.upload.return_value = {"ok": True, "key": "path/to/image.jpg", "size": 100}

        # Mock image file
        mock_image_file = MagicMock()
        mock_image_file.name = "test_image.jpg"
        mock_image_file.size = 100
        mock_image_file.content_type = "image/jpeg"

        result = self.catalog_service.create_product(data=data, user=self.seller_user, images=[mock_image_file])
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.value)
        self.assertEqual(result.value.name, "New Product")
        self.assertEqual(Product.objects.count(), 2)
        self.assertTrue(ProductImage.objects.filter(product=result.value).exists())
        self.mock_storage.upload.assert_called_once()

    @patch("marketplace.catalog.domain.services.catalog_service.is_seller", return_value=False)
    def test_create_product_permission_denied(self, mock_is_seller):
        data = {
            "name": "Unauthorized Product",
            "description": "New Description",
            "price": "50.00",
            "category_id": self.category.id,
            "stock_quantity": 5,
            "condition": "new",
        }
        result = self.catalog_service.create_product(data=data, user=self.buyer_user)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.PERMISSION_DENIED)
        self.assertEqual(Product.objects.count(), 1)  # No new product created

    @patch(
        "marketplace.catalog.domain.services.catalog_service.is_seller", return_value=True
    )  # Seller is allowed to update
    def test_update_product_success(self, mock_is_seller):
        update_data = {"name": "Updated Product Name", "price": "150.00"}
        result = self.catalog_service.update_product(
            product_id=str(self.product.id), data=update_data, user=self.seller_user
        )
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.value)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Updated Product Name")
        self.assertEqual(self.product.price, Decimal("150.00"))

    def test_update_product_not_owner_permission_denied(self):
        update_data = {"name": "Hacked Product Name"}
        result = self.catalog_service.update_product(
            product_id=str(self.product.id), data=update_data, user=self.buyer_user
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.NOT_PRODUCT_OWNER)
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.name, "Hacked Product Name")  # Name should not be updated

    @patch(
        "marketplace.catalog.domain.services.catalog_service.is_seller", return_value=True
    )  # Seller is allowed to delete
    def test_delete_product_soft_delete_success(self, mock_is_seller):
        result = self.catalog_service.delete_product(product_id=str(self.product.id), user=self.seller_user)
        self.assertTrue(result.ok)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)  # Product should be soft deleted

    @patch(
        "marketplace.catalog.domain.services.catalog_service.is_seller", return_value=True
    )  # Seller is allowed to delete
    def test_delete_product_hard_delete_success(self, mock_is_seller):
        # Create another product to ensure only one is deleted
        Product.objects.create(
            name="Another Product",
            slug="another-product",
            description="Another Desc",
            price=50.00,
            seller=self.seller_user,
            category=self.category,
            stock_quantity=5,
            is_active=True,
        )
        self.assertEqual(Product.objects.count(), 2)
        result = self.catalog_service.delete_product(
            product_id=str(self.product.id), user=self.seller_user, hard_delete=True
        )
        self.assertTrue(result.ok)
        self.assertEqual(Product.objects.count(), 1)  # Original product should be hard deleted
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

    def test_delete_product_not_owner_permission_denied(self):
        result = self.catalog_service.delete_product(product_id=str(self.product.id), user=self.buyer_user)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, ErrorCodes.NOT_PRODUCT_OWNER)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)  # Product should not be deleted
