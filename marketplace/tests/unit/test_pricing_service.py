from decimal import Decimal
from unittest.mock import Mock

import pytest

from marketplace.models import Product
from marketplace.services.pricing_service import PricingService


@pytest.mark.unit
class TestPricingServiceUnit:
    def setup_method(self):
        self.service = PricingService()

        # Mock Product
        self.product = Mock(spec=Product)
        self.product.id = "product-uuid"
        self.product.price = Decimal("100.00")
        self.product.original_price = None
        self.product.is_active = True

    def test_is_on_sale_false(self):
        result = self.service.is_on_sale(self.product)
        assert result.ok
        assert result.value is False

    def test_is_on_sale_true(self):
        self.product.original_price = Decimal("120.00")
        result = self.service.is_on_sale(self.product)
        assert result.ok
        assert result.value is True

    def test_calculate_discount_percentage(self):
        self.product.original_price = Decimal("200.00")
        self.product.price = Decimal("100.00")

        result = self.service.calculate_discount_percentage(self.product)
        assert result.ok
        assert result.value == Decimal("50.00")

    def test_calculate_cart_total_empty(self):
        result = self.service.calculate_cart_total([])
        assert result.ok
        assert result.value["total"] == Decimal("0")
        assert result.value["items_count"] == 0

    def test_calculate_cart_total_single_item(self):
        item = {"product": self.product, "quantity": 2}
        # 100 * 2 = 200
        # Tax (10%) = 20
        # Total = 220

        result = self.service.calculate_cart_total([item])
        assert result.ok
        assert result.value["subtotal"] == Decimal("200.00")
        assert result.value["tax"] == Decimal("20.00")
        assert result.value["total"] == Decimal("220.00")
        assert result.value["items_count"] == 1

    def test_calculate_order_total_with_shipping_and_coupon(self):
        items = [{"product": self.product, "quantity": 1}]
        # Subtotal: 100
        # Coupon: 10 -> Adjusted Subtotal: 90
        # Tax (10% of 90): 9
        # Shipping: 15
        # Total: 90 + 9 + 15 = 114

        result = self.service.calculate_order_total(
            items, shipping_cost=Decimal("15.00"), coupon_discount=Decimal("10.00")
        )

        assert result.ok
        assert result.value["subtotal"] == Decimal("100.00")
        assert result.value["subtotal_after_discount"] == Decimal("90.00")
        assert result.value["tax"] == Decimal("9.00")
        assert result.value["shipping"] == Decimal("15.00")
        assert result.value["total"] == Decimal("114.00")
