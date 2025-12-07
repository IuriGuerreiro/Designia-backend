import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.db.models import QuerySet

from marketplace.models import Product
from marketplace.services.search_service import ErrorCodes, SearchService


@pytest.fixture
def search_service():
    return SearchService()


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

    # Create a list of mock products and attach to qs so tests can modify it
    qs.mock_products = [MagicMock(spec=Product) for _ in range(10)]

    # Configure iterator
    qs.__iter__.side_effect = lambda: iter(qs.mock_products)

    # Configure slicing (__getitem__) to return the list
    qs.__getitem__.side_effect = lambda k: qs.mock_products[k] if isinstance(k, slice) else qs.mock_products[k]

    qs.exists.return_value = True
    return qs


@pytest.mark.unit
class TestSearchService:
    @patch("marketplace.services.search_service.Product.objects")
    @patch("marketplace.services.search_service.Paginator")
    def test_search_success(self, mock_paginator, mock_product_objects, search_service, mock_product_qs):
        # Setup mocks
        mock_product_objects.select_related.return_value = mock_product_qs
        mock_page = MagicMock()
        mock_page.object_list = [MagicMock(spec=Product)]
        mock_page.has_next.return_value = True
        mock_page.has_previous.return_value = False

        paginator_instance = MagicMock()
        paginator_instance.count = 100
        paginator_instance.num_pages = 5
        paginator_instance.get_page.return_value = mock_page
        mock_paginator.return_value = paginator_instance

        # Execute
        result = search_service.search(query="test", filters={"price_min": 10}, page=1)

        # Assert
        assert result.ok is True
        assert result.value["count"] == 100
        assert result.value["page"] == 1

        # Verify calls
        mock_product_objects.select_related.assert_called()
        mock_product_qs.filter.assert_called()  # Should be called for filters

    @patch("marketplace.services.search_service.Product.objects")
    def test_search_error(self, mock_product_objects, search_service):
        mock_product_objects.select_related.side_effect = Exception("Database error")

        result = search_service.search(query="test")

        assert result.ok is False
        assert result.error == ErrorCodes.INTERNAL_ERROR
        assert "Database error" in result.error_detail

    @patch("marketplace.services.search_service.Product.objects")
    def test_autocomplete_success(self, mock_product_objects, search_service, mock_product_qs):
        mock_product_objects.filter.return_value = mock_product_qs
        # Set specific mock products
        product = MagicMock(spec=Product)
        product.id = uuid.uuid4()
        product.name = "Test Product"
        product.price = Decimal("100.00")
        product.category.name = "Cat"

        mock_product_qs.mock_products = [product]

        result = search_service.autocomplete(query="tes")

        assert result.ok is True
        assert len(result.value) == 1
        assert result.value[0]["name"] == "Test Product"

    def test_autocomplete_empty_query(self, search_service):
        result = search_service.autocomplete(query="a")
        assert result.ok is True
        assert result.value == []

    @patch("marketplace.services.search_service.Product.objects")
    def test_autocomplete_error(self, mock_product_objects, search_service):
        mock_product_objects.filter.side_effect = Exception("DB Error")
        result = search_service.autocomplete(query="test")
        assert result.ok is False
        assert result.error == ErrorCodes.INTERNAL_ERROR

    @patch("marketplace.services.search_service.Category.objects")
    @patch("marketplace.services.search_service.Product.objects")
    def test_get_suggestions_success(self, mock_product_objects, mock_category_objects, search_service):
        # Mock categories
        mock_category_qs = MagicMock()
        mock_category_qs.values_list.return_value = ["Electronics"]
        mock_category_objects.filter.return_value = mock_category_qs

        # Mock brands
        mock_product_qs = MagicMock()
        mock_product_qs.values_list.return_value.distinct.return_value = ["Apple"]
        mock_product_objects.filter.return_value = mock_product_qs

        result = search_service.get_suggestions(query="app")

        assert result.ok is True
        assert "Electronics" in result.value
        assert "Apple" in result.value

    def test_get_suggestions_empty_query(self, search_service):
        result = search_service.get_suggestions(query="a")
        assert result.ok is True
        assert result.value == []

    @patch("marketplace.services.search_service.Product.objects")
    @patch("marketplace.services.search_service.Paginator")
    def test_filter_products_success(self, mock_paginator, mock_product_objects, search_service, mock_product_qs):
        mock_product_objects.select_related.return_value = mock_product_qs

        mock_page = MagicMock()
        mock_page.object_list = []
        paginator_instance = MagicMock()
        paginator_instance.get_page.return_value = mock_page
        mock_paginator.return_value = paginator_instance

        result = search_service.filter_products(filters={"in_stock": True})

        assert result.ok is True
        mock_product_qs.filter.assert_called()  # Check if filtering was applied

    @patch("marketplace.services.search_service.Product.objects")
    def test_get_trending_products_success(self, mock_product_objects, search_service, mock_product_qs):
        mock_product_objects.filter.return_value = mock_product_qs
        # Set 5 items
        mock_product_qs.mock_products = [MagicMock(spec=Product) for _ in range(5)]

        result = search_service.get_trending_products(limit=5)

        assert result.ok is True
        assert len(result.value) == 5

    @patch("marketplace.services.search_service.Product.objects")
    def test_get_related_products_success(self, mock_product_objects, search_service, mock_product_qs):
        # Setup mock for getting reference product
        mock_product = MagicMock(spec=Product, id=uuid.uuid4(), price=Decimal("100.00"), brand="BrandX")
        mock_product_objects.get.return_value = mock_product

        # Setup mock for related products query
        mock_product_objects.filter.return_value = mock_product_qs
        # Set 3 items
        mock_product_qs.mock_products = [MagicMock(spec=Product) for _ in range(3)]

        result = search_service.get_related_products(product_id=str(mock_product.id))

        assert result.ok is True
        assert len(result.value) == 3

    @patch("marketplace.services.search_service.Product.objects")
    def test_get_related_products_not_found(self, mock_product_objects, search_service):
        mock_product_objects.get.side_effect = Product.DoesNotExist
        result = search_service.get_related_products(product_id=str(uuid.uuid4()))
        assert result.ok is False
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @patch("django.db.connection")
    def test_check_postgres_support(self, mock_connection, search_service):
        mock_connection.vendor = "postgresql"
        assert search_service._check_postgres_support() is True

        mock_connection.vendor = "sqlite"
        assert search_service._check_postgres_support() is False

    @patch("marketplace.services.search_service.Product.objects")
    def test_apply_filters_all(self, mock_product_objects, search_service, mock_product_qs):
        filters = {
            "category": "electronics",
            "price_min": 100,
            "price_max": 500,
            "seller": uuid.uuid4(),
            "min_rating": 4,
            "in_stock": True,
            "condition": "new",
            "brand": "Apple",
            "is_featured": True,
            "is_active": True,
        }

        search_service._apply_filters(mock_product_qs, filters)

        # Verify filter calls were made
        assert mock_product_qs.filter.call_count >= 5
        assert mock_product_qs.annotate.call_count >= 1  # for rating

    def test_apply_sorting(self, search_service, mock_product_qs):
        # Test each sort option
        search_service._apply_sorting(mock_product_qs, "price_asc", None)
        mock_product_qs.order_by.assert_called_with("price", "-created_at")

        search_service._apply_sorting(mock_product_qs, "price_desc", None)
        mock_product_qs.order_by.assert_called_with("-price", "-created_at")

        search_service._apply_sorting(mock_product_qs, "rating", None)
        mock_product_qs.annotate.assert_called()  # Should annotate avg_rating
