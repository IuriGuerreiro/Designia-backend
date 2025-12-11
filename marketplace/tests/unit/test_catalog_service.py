import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.db.models import QuerySet

from marketplace.catalog.domain.services.catalog_service import CatalogService, ErrorCodes
from marketplace.models import Category, Product


@pytest.fixture
def mock_storage():
    return MagicMock()


@pytest.fixture
def catalog_service(mock_storage):
    return CatalogService(storage=mock_storage)


@pytest.fixture
def mock_product_qs():
    qs = MagicMock(spec=QuerySet)
    qs.select_related.return_value = qs
    qs.prefetch_related.return_value = qs
    qs.annotate.return_value = qs
    qs.filter.return_value = qs
    qs.exclude.return_value = qs
    qs.order_by.return_value = qs
    qs.count.return_value = 10

    # Configure mock products list for iteration and slicing
    qs.mock_products = [MagicMock(spec=Product) for _ in range(10)]
    qs.__iter__.side_effect = lambda: iter(qs.mock_products)
    qs.__getitem__.side_effect = lambda k: qs.mock_products[k] if isinstance(k, slice) else qs.mock_products[k]

    qs.exists.return_value = True
    return qs


@pytest.mark.unit
class TestCatalogService:
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    @patch("marketplace.catalog.domain.services.catalog_service.Paginator")
    def test_list_products_success(self, mock_paginator, mock_product_objects, catalog_service, mock_product_qs):
        mock_product_objects.select_related.return_value = mock_product_qs

        mock_page = MagicMock()
        mock_page.object_list = [MagicMock(spec=Product)]
        paginator_instance = MagicMock()
        paginator_instance.count = 100
        paginator_instance.num_pages = 5
        paginator_instance.get_page.return_value = mock_page
        mock_paginator.return_value = paginator_instance

        result = catalog_service.list_products(filters={"category": "electronics"}, page=1)

        assert result.ok is True
        assert result.value["count"] == 100
        mock_product_qs.filter.assert_called()

    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_get_product_success(self, mock_product_objects, catalog_service, mock_product_qs):
        mock_product = MagicMock(spec=Product, id=uuid.uuid4(), name="Test")
        mock_product_qs.get.return_value = mock_product
        mock_product_objects.select_related.return_value = mock_product_qs

        result = catalog_service.get_product(str(mock_product.id))

        assert result.ok is True
        assert result.value == mock_product
        mock_product.save.assert_called()  # View count updated

    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_get_product_not_found(self, mock_product_objects, catalog_service, mock_product_qs):
        mock_product_qs.get.side_effect = Product.DoesNotExist
        mock_product_objects.select_related.return_value = mock_product_qs

        result = catalog_service.get_product("invalid-id")

        assert result.ok is False
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.is_seller")
    @patch("marketplace.catalog.domain.services.catalog_service.Category.objects")
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_create_product_success(
        self, mock_product_objects, mock_category_objects, mock_is_seller, catalog_service
    ):
        mock_is_seller.return_value = True
        mock_user = MagicMock()

        mock_category = MagicMock(spec=Category)
        mock_category_objects.get.return_value = mock_category

        mock_product = MagicMock(spec=Product)
        mock_product_objects.create.return_value = mock_product

        data = {"name": "New Product", "price": Decimal("100.00"), "category_id": "cat-id", "stock_quantity": 10}

        result = catalog_service.create_product(data, mock_user)

        assert result.ok is True
        assert result.value == mock_product
        mock_product_objects.create.assert_called()

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.is_seller")
    def test_create_product_not_seller(self, mock_is_seller, catalog_service):
        mock_is_seller.return_value = False
        result = catalog_service.create_product({}, MagicMock())
        assert result.ok is False
        assert result.error == ErrorCodes.PERMISSION_DENIED

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_update_product_success(self, mock_product_objects, catalog_service):
        mock_product = MagicMock(spec=Product)
        mock_user = MagicMock()
        mock_product.seller = mock_user  # Same user

        mock_qs = MagicMock()
        mock_qs.get.return_value = mock_product
        mock_product_objects.select_for_update.return_value = mock_qs

        result = catalog_service.update_product("prod-id", {"name": "Updated Name"}, mock_user)

        assert result.ok is True
        assert mock_product.name == "Updated Name"
        mock_product.save.assert_called()

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_update_product_permission_denied(self, mock_product_objects, catalog_service):
        mock_product = MagicMock(spec=Product)
        mock_product.seller = MagicMock()  # Different user
        mock_user = MagicMock()

        mock_qs = MagicMock()
        mock_qs.get.return_value = mock_product
        mock_product_objects.select_for_update.return_value = mock_qs

        result = catalog_service.update_product("prod-id", {}, mock_user)

        assert result.ok is False
        assert result.error == ErrorCodes.NOT_PRODUCT_OWNER

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_delete_product_soft(self, mock_product_objects, catalog_service):
        mock_product = MagicMock(spec=Product)
        mock_user = MagicMock()
        mock_product.seller = mock_user

        mock_qs = MagicMock()
        mock_qs.get.return_value = mock_product
        mock_product_objects.select_for_update.return_value = mock_qs

        result = catalog_service.delete_product("prod-id", mock_user, hard_delete=False)

        assert result.ok is True
        assert mock_product.is_active is False
        mock_product.save.assert_called()

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_delete_product_hard(self, mock_product_objects, catalog_service):
        mock_product = MagicMock(spec=Product)
        mock_user = MagicMock()
        mock_product.seller = mock_user

        mock_qs = MagicMock()
        mock_qs.get.return_value = mock_product
        mock_product_objects.select_for_update.return_value = mock_qs

        result = catalog_service.delete_product("prod-id", mock_user, hard_delete=True)

        assert result.ok is True
        mock_product.delete.assert_called()

    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_search_products(self, mock_product_objects, catalog_service, mock_product_qs):
        mock_product_objects.select_related.return_value = mock_product_qs

        result = catalog_service.search_products(query="iphone")

        assert result.ok is True
        mock_product_qs.filter.assert_called()

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.ProductImage.objects")
    @patch("marketplace.catalog.domain.services.catalog_service.is_seller")
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_create_product_with_images(
        self, mock_product_objects, mock_is_seller, mock_image_objects, catalog_service, mock_storage
    ):
        mock_is_seller.return_value = True
        mock_product_objects.create.return_value = MagicMock(spec=Product, id=uuid.uuid4())
        mock_storage.upload.return_value = {"ok": True}

        image_file = MagicMock()
        image_file.name = "test.jpg"

        result = catalog_service.create_product({"name": "Test", "price": 10}, MagicMock(), images=[image_file])

        assert result.ok is True
        mock_storage.upload.assert_called()
        mock_image_objects.create.assert_called()

    @pytest.mark.django_db
    @patch("marketplace.catalog.domain.services.catalog_service.Product.objects")
    def test_create_product_image_fail(self, mock_product_objects, catalog_service, mock_storage):
        # We need to setup a product creation flow that fails at image upload
        with patch("marketplace.catalog.domain.services.catalog_service.is_seller", return_value=True):
            mock_product = MagicMock(spec=Product)
            mock_product_objects.create.return_value = mock_product
            # Make upload raise exception to trigger service error in _upload_product_images
            mock_storage.upload.side_effect = Exception("Critical upload error")

            image_file = MagicMock()
            image_file.name = "test.jpg"
            image_file.content_type = "image/jpeg"

            result = catalog_service.create_product({"name": "Test", "price": 10}, MagicMock(), images=[image_file])

            assert result.ok is False
            mock_product.delete.assert_called()  # Rollback deletion
