from unittest.mock import MagicMock, Mock, patch

import pytest

from marketplace.models import Product
from marketplace.services.inventory_service import ErrorCodes, InventoryService


@pytest.mark.unit
class TestInventoryServiceUnit:
    def setup_method(self):
        self.service = InventoryService()
        self.product_id = "test-product-id"

    @patch("marketplace.models.Product.objects.get")
    def test_check_availability_success(self, mock_get):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 10
        mock_get.return_value = mock_product

        result = self.service.check_availability(self.product_id, quantity=5)
        assert result.ok
        assert result.value is True

    @patch("marketplace.models.Product.objects.get")
    def test_check_availability_insufficient(self, mock_get):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 3
        mock_get.return_value = mock_product

        result = self.service.check_availability(self.product_id, quantity=5)
        assert result.ok
        assert result.value is False

    @patch("marketplace.models.Product.objects.get")
    def test_is_in_stock(self, mock_get):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 1
        mock_get.return_value = mock_product

        result = self.service.is_in_stock(self.product_id)
        assert result.ok
        assert result.value is True

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_reserve_stock_success(self, mock_select_for_update):
        # Mock chain: Product.objects.select_for_update().get()
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 10
        mock_product.name = "Test Product"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.reserve_stock(self.product_id, quantity=2)

        assert result.ok
        assert result.value["new_stock"] == 8
        mock_product.save.assert_called_once()

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_reserve_stock_insufficient(self, mock_select_for_update):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 1
        mock_product.name = "Test Product"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.reserve_stock(self.product_id, quantity=2)

        assert not result.ok
        assert result.error == ErrorCodes.INSUFFICIENT_STOCK
        mock_product.save.assert_not_called()

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_release_stock(self, mock_select_for_update):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 5
        mock_product.name = "Test Product"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.release_stock(self.product_id, quantity=2)

        assert result.ok
        assert result.value["new_stock"] == 7
        mock_product.save.assert_called_once()

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_set(self, mock_select_for_update):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 10
        mock_product.name = "Test Product"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=50, operation="set")

        assert result.ok
        assert result.value["new_stock"] == 50
        mock_product.save.assert_called_once()

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_add(self, mock_select_for_update):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 10
        mock_product.name = "Test Product"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=5, operation="add")

        assert result.ok
        assert result.value["new_stock"] == 15
        mock_product.save.assert_called_once()

    @patch("marketplace.models.Product.objects.get")
    def test_get_stock_level(self, mock_get):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 100
        mock_get.return_value = mock_product

        result = self.service.get_stock_level(self.product_id)
        assert result.ok
        assert result.value == 100

    def test_check_availability_negative_quantity(self):
        result = self.service.check_availability(self.product_id, quantity=-1)
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_QUANTITY

    @patch("marketplace.models.Product.objects.get")
    def test_check_availability_not_found(self, mock_get):
        mock_get.side_effect = Product.DoesNotExist
        result = self.service.check_availability(self.product_id)
        assert not result.ok
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @patch("marketplace.models.Product.objects.get")
    def test_check_availability_error(self, mock_get):
        mock_get.side_effect = Exception("DB Error")
        result = self.service.check_availability(self.product_id)
        assert not result.ok
        assert result.error == ErrorCodes.INTERNAL_ERROR

    @pytest.mark.django_db
    def test_reserve_stock_negative_quantity(self):
        result = self.service.reserve_stock(self.product_id, quantity=-1)
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_QUANTITY

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_reserve_stock_not_found(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = Product.DoesNotExist
        mock_select_for_update.return_value = mock_queryset

        result = self.service.reserve_stock(self.product_id, quantity=1)
        assert not result.ok
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_reserve_stock_error(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = Exception("DB Error")
        mock_select_for_update.return_value = mock_queryset

        result = self.service.reserve_stock(self.product_id, quantity=1)
        assert not result.ok
        assert result.error == ErrorCodes.RESERVATION_FAILED

    @pytest.mark.django_db
    def test_release_stock_negative_quantity(self):
        result = self.service.release_stock(self.product_id, quantity=-1)
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_QUANTITY

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_release_stock_not_found(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = Product.DoesNotExist
        mock_select_for_update.return_value = mock_queryset

        result = self.service.release_stock(self.product_id, quantity=1)
        assert not result.ok
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_release_stock_error(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = Exception("DB Error")
        mock_select_for_update.return_value = mock_queryset

        result = self.service.release_stock(self.product_id, quantity=1)
        assert not result.ok
        assert result.error == ErrorCodes.INTERNAL_ERROR

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_subtract_success(self, mock_select_for_update):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 10
        mock_product.name = "Test Product"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=5, operation="subtract")

        assert result.ok
        assert result.value["new_stock"] == 5
        mock_product.save.assert_called_once()

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_subtract_insufficient(self, mock_select_for_update):
        mock_product = Mock(spec=Product)
        mock_product.stock_quantity = 3

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_product
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=5, operation="subtract")

        assert not result.ok
        assert result.error == ErrorCodes.INSUFFICIENT_STOCK

    @pytest.mark.django_db
    def test_update_stock_invalid_operation(self):
        result = self.service.update_stock(self.product_id, quantity=5, operation="multiply")
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_INPUT

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_set_negative(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.return_value = Mock(spec=Product)
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=-5, operation="set")
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_QUANTITY

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_add_negative(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.return_value = Mock(spec=Product)
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=-5, operation="add")
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_QUANTITY

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_subtract_negative(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.return_value = Mock(spec=Product)
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=-5, operation="subtract")
        assert not result.ok
        assert result.error == ErrorCodes.INVALID_QUANTITY

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_not_found(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = Product.DoesNotExist
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=1, operation="set")
        assert not result.ok
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @pytest.mark.django_db
    @patch("marketplace.models.Product.objects.select_for_update")
    def test_update_stock_error(self, mock_select_for_update):
        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = Exception("DB Error")
        mock_select_for_update.return_value = mock_queryset

        result = self.service.update_stock(self.product_id, quantity=1, operation="set")
        assert not result.ok
        assert result.error == ErrorCodes.INTERNAL_ERROR

    @patch("marketplace.models.Product.objects.get")
    def test_is_in_stock_not_found(self, mock_get):
        mock_get.side_effect = Product.DoesNotExist
        result = self.service.is_in_stock(self.product_id)
        assert not result.ok
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @patch("marketplace.models.Product.objects.get")
    def test_is_in_stock_error(self, mock_get):
        mock_get.side_effect = Exception("DB Error")
        result = self.service.is_in_stock(self.product_id)
        assert not result.ok
        assert result.error == ErrorCodes.INTERNAL_ERROR

    @patch("marketplace.models.Product.objects.get")
    def test_get_stock_level_not_found(self, mock_get):
        mock_get.side_effect = Product.DoesNotExist
        result = self.service.get_stock_level(self.product_id)
        assert not result.ok
        assert result.error == ErrorCodes.PRODUCT_NOT_FOUND

    @patch("marketplace.models.Product.objects.get")
    def test_get_stock_level_error(self, mock_get):
        mock_get.side_effect = Exception("DB Error")
        result = self.service.get_stock_level(self.product_id)
        assert not result.ok
        assert result.error == ErrorCodes.INTERNAL_ERROR
