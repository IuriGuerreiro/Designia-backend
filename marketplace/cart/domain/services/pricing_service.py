"""
PricingService - Price Calculations

Handles all pricing logic including discounts, sales, taxes, and totals.
All calculations use Decimal for precision (no floating point errors).

Story 2.6: PricingService - Price Calculations
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from django.conf import settings

from marketplace.catalog.domain.models.catalog import Product
from marketplace.catalog.domain.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok


logger = logging.getLogger(__name__)


class PricingService(BaseService):
    """
    Service for calculating prices, discounts, and totals.

    Responsibilities:
    - Calculate product prices (sale prices, discounts)
    - Calculate cart totals
    - Calculate order totals (with shipping and tax)
    - Apply coupon codes (future)
    - Calculate seller payouts (future)

    All methods are stateless (pure functions) for easy testing.
    """

    def __init__(self):
        """Initialize PricingService."""
        super().__init__()
        # Tax rates by region (can be moved to database later)
        self.tax_rates = getattr(settings, "TAX_RATES", {"default": Decimal("0.10")})  # 10% default

    @BaseService.log_performance
    def calculate_product_price(self, product: Product) -> ServiceResult[Dict[str, Decimal]]:
        """
        Calculate pricing details for a product.

        Args:
            product: Product instance

        Returns:
            ServiceResult with pricing breakdown

        Example:
            >>> result = pricing_service.calculate_product_price(product)
            >>> if result.ok:
            ...     price_info = result.value
            ...     print(f"Price: {price_info['price']}")
            ...     print(f"On sale: {price_info['is_on_sale']}")
        """
        try:
            price = Decimal(str(product.price))
            original_price = Decimal(str(product.original_price)) if product.original_price else None

            is_on_sale = original_price is not None and original_price > price
            discount_amount = (original_price - price) if is_on_sale else Decimal("0")
            discount_percentage = self.calculate_discount_percentage(product).value if is_on_sale else Decimal("0")

            pricing = {
                "price": price,
                "original_price": original_price,
                "is_on_sale": is_on_sale,
                "discount_amount": discount_amount,
                "discount_percentage": discount_percentage,
                "currency": "USD",  # TODO: Multi-currency support
            }

            return service_ok(pricing)

        except Exception as e:
            self.logger.error(f"Error calculating price for product {product.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def calculate_discount_percentage(self, product: Product) -> ServiceResult[Decimal]:
        """
        Calculate discount percentage for a product.

        Args:
            product: Product instance

        Returns:
            ServiceResult with discount percentage (0-100)

        Example:
            >>> result = pricing_service.calculate_discount_percentage(product)
            >>> if result.ok:
            ...     print(f"Discount: {result.value}%")
        """
        try:
            if not product.original_price or product.original_price <= product.price:
                return service_ok(Decimal("0"))

            original = Decimal(str(product.original_price))
            current = Decimal(str(product.price))

            # Calculate percentage: ((original - current) / original) * 100
            discount_percentage = ((original - current) / original * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            return service_ok(discount_percentage)

        except Exception as e:
            self.logger.error(f"Error calculating discount for product {product.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def is_on_sale(self, product: Product) -> ServiceResult[bool]:
        """
        Check if a product is on sale.

        Args:
            product: Product instance

        Returns:
            ServiceResult with True if on sale, False otherwise

        Example:
            >>> result = pricing_service.is_on_sale(product)
            >>> if result.ok and result.value:
            ...     print("Product is on sale!")
        """
        try:
            on_sale = product.original_price is not None and Decimal(str(product.original_price)) > Decimal(
                str(product.price)
            )
            return service_ok(on_sale)
        except Exception as e:
            self.logger.error(f"Error checking sale status for product {product.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def calculate_cart_total(
        self, cart_items: List[Dict], region: str = "default"
    ) -> ServiceResult[Dict[str, Decimal]]:
        """
        Calculate total for a shopping cart.

        Args:
            cart_items: List of dicts with 'product' (Product instance) and 'quantity' (int)
            region: Region for tax calculation (default: "default")

        Returns:
            ServiceResult with cart total breakdown

        Example:
            >>> cart_items = [
            ...     {"product": product1, "quantity": 2},
            ...     {"product": product2, "quantity": 1},
            ... ]
            >>> result = pricing_service.calculate_cart_total(cart_items)
            >>> if result.ok:
            ...     total_info = result.value
            ...     print(f"Total: ${total_info['total']}")
        """
        try:
            if not cart_items:
                return service_ok(
                    {
                        "subtotal": Decimal("0"),
                        "tax": Decimal("0"),
                        "total": Decimal("0"),
                        "items_count": 0,
                        "savings": Decimal("0"),
                    }
                )

            subtotal = Decimal("0")
            original_subtotal = Decimal("0")

            for item in cart_items:
                product = item.get("product")
                quantity = item.get("quantity", 1)

                if not product:
                    return service_err(ErrorCodes.INVALID_INPUT, "Cart item missing product")

                if quantity <= 0:
                    return service_err(ErrorCodes.INVALID_QUANTITY, f"Invalid quantity: {quantity}")

                # Calculate item total
                price = Decimal(str(product.price))
                item_total = price * quantity
                subtotal += item_total

                # Track original prices for savings calculation
                if product.original_price:
                    original_subtotal += Decimal(str(product.original_price)) * quantity
                else:
                    original_subtotal += item_total

            # Calculate tax
            tax_rate = self.tax_rates.get(region, self.tax_rates["default"])
            tax = (subtotal * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Calculate total
            total = subtotal + tax

            # Calculate savings
            savings = (original_subtotal - subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            cart_total = {
                "subtotal": subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "tax": tax,
                "tax_rate": tax_rate,
                "total": total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "items_count": len(cart_items),
                "savings": savings,
                "currency": "USD",
            }

            self.logger.info(f"Cart total calculated: items={len(cart_items)}, total=${total}")

            return service_ok(cart_total)

        except Exception as e:
            self.logger.error(f"Error calculating cart total: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def calculate_order_total(
        self,
        order_items: List[Dict],
        shipping_cost: Decimal = Decimal("0"),
        region: str = "default",
        coupon_discount: Decimal = Decimal("0"),
    ) -> ServiceResult[Dict[str, Decimal]]:
        """
        Calculate total for an order (with shipping and optional coupon).

        Args:
            order_items: List of dicts with 'product' and 'quantity'
            shipping_cost: Shipping cost (default: 0)
            region: Region for tax calculation
            coupon_discount: Discount amount from coupon (default: 0)

        Returns:
            ServiceResult with order total breakdown

        Example:
            >>> result = pricing_service.calculate_order_total(
            ...     order_items,
            ...     shipping_cost=Decimal("10.00"),
            ...     coupon_discount=Decimal("5.00")
            ... )
        """
        try:
            # Start with cart total
            cart_result = self.calculate_cart_total(order_items, region)
            if not cart_result.ok:
                return cart_result

            cart_total = cart_result.value

            # Apply coupon discount to subtotal
            subtotal_after_coupon = max(cart_total["subtotal"] - coupon_discount, Decimal("0"))

            # Recalculate tax on discounted subtotal
            tax_rate = cart_total["tax_rate"]
            tax = (subtotal_after_coupon * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Calculate final total
            total = subtotal_after_coupon + tax + shipping_cost

            order_total = {
                "subtotal": cart_total["subtotal"],
                "coupon_discount": coupon_discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "subtotal_after_discount": subtotal_after_coupon.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "tax": tax,
                "tax_rate": tax_rate,
                "shipping": shipping_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "total": total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "items_count": cart_total["items_count"],
                "savings": cart_total["savings"] + coupon_discount,
                "currency": "USD",
            }

            self.logger.info(
                f"Order total calculated: items={cart_total['items_count']}, shipping=${shipping_cost}, total=${total}"
            )

            return service_ok(order_total)

        except Exception as e:
            self.logger.error(f"Error calculating order total: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def calculate_shipping_cost(
        self, weight_kg: Optional[Decimal] = None, distance_km: Optional[Decimal] = None
    ) -> ServiceResult[Decimal]:
        """
        Calculate shipping cost based on weight and/or distance.

        Currently uses flat rate. Can be extended to weight-based or distance-based.

        Args:
            weight_kg: Total weight in kilograms
            distance_km: Shipping distance in kilometers

        Returns:
            ServiceResult with shipping cost

        Example:
            >>> result = pricing_service.calculate_shipping_cost(weight_kg=Decimal("2.5"))
            >>> if result.ok:
            ...     print(f"Shipping: ${result.value}")
        """
        try:
            # TODO: Implement weight-based and distance-based shipping
            # For now, use flat rate
            flat_rate = Decimal(str(getattr(settings, "SHIPPING_FLAT_RATE", "10.00")))

            self.logger.info(f"Shipping cost calculated: flat_rate=${flat_rate}")

            return service_ok(flat_rate)

        except Exception as e:
            self.logger.error(f"Error calculating shipping cost: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def validate_coupon(self, coupon_code: str, cart_total: Decimal) -> ServiceResult[Dict]:
        """
        Validate a coupon code and calculate discount.

        Placeholder for future coupon system.

        Args:
            coupon_code: Coupon code to validate
            cart_total: Cart subtotal

        Returns:
            ServiceResult with coupon details or error

        Example:
            >>> result = pricing_service.validate_coupon("SAVE10", Decimal("100.00"))
            >>> if result.ok:
            ...     discount = result.value["discount_amount"]
        """
        # TODO: Implement coupon validation system
        # This would check database for valid coupons, expiration, usage limits, etc.

        self.logger.warning(f"Coupon validation not yet implemented: {coupon_code}")

        return service_err("coupon_not_supported", "Coupon system not yet implemented")
