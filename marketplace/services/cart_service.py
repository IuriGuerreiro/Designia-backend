"""
CartService - Shopping Cart Operations

Handles shopping cart operations including add, remove, update, and clear.
Validates stock availability and calculates totals using InventoryService and PricingService.

Story 2.3: CartService - Shopping Cart Operations
"""

import logging
from typing import Dict

from django.contrib.auth import get_user_model
from django.db import transaction

from marketplace.models import Cart, CartItem, Product

from .base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from .inventory_service import InventoryService
from .pricing_service import PricingService

User = get_user_model()
logger = logging.getLogger(__name__)


class CartService(BaseService):
    """
    Service for managing shopping cart operations.

    Responsibilities:
    - Get user's cart
    - Add items to cart (with stock validation)
    - Remove items from cart
    - Update item quantities
    - Clear cart
    - Calculate cart totals

    Dependencies:
    - InventoryService: Check stock availability
    - PricingService: Calculate cart totals
    """

    def __init__(self, inventory_service: InventoryService = None, pricing_service: PricingService = None):
        """
        Initialize CartService.

        Args:
            inventory_service: Service for stock management (injected)
            pricing_service: Service for price calculations (injected)
        """
        super().__init__()
        self.inventory_service = inventory_service or InventoryService()
        self.pricing_service = pricing_service or PricingService()

    @BaseService.log_performance
    def get_cart(self, user: User) -> ServiceResult[Dict]:
        """
        Get user's shopping cart with items and totals.

        Args:
            user: User whose cart to retrieve

        Returns:
            ServiceResult with cart data including items and totals

        Example:
            >>> result = cart_service.get_cart(user)
            >>> if result.ok:
            ...     cart_data = result.value
            ...     items = cart_data["items"]
            ...     total = cart_data["totals"]["total"]
        """
        try:
            # Get or create cart
            cart, created = Cart.objects.get_or_create(user=user)

            # Get cart items with related data
            cart_items = cart.items.select_related("product", "product__category", "product__seller").prefetch_related(
                "product__images"
            )

            # Build item data
            items_data = []
            cart_items_for_pricing = []

            for cart_item in cart_items:
                item_data = {
                    "id": cart_item.id,
                    "product": cart_item.product,
                    "quantity": cart_item.quantity,
                    "added_at": cart_item.added_at,
                }
                items_data.append(item_data)

                # Prepare for pricing calculation
                cart_items_for_pricing.append({"product": cart_item.product, "quantity": cart_item.quantity})

            # Calculate totals
            totals_result = self.pricing_service.calculate_cart_total(cart_items_for_pricing)
            if not totals_result.ok:
                self.logger.warning(f"Failed to calculate cart totals for user {user.id}: {totals_result.error}")
                totals = {}
            else:
                totals = totals_result.value

            cart_data = {
                "id": cart.id,
                "user_id": user.id,
                "items": items_data,
                "items_count": len(items_data),
                "totals": totals,
                "created_at": cart.created_at,
                "updated_at": cart.updated_at,
            }

            self.logger.info(f"Retrieved cart for user {user.id}: {len(items_data)} items")

            return service_ok(cart_data)

        except Exception as e:
            self.logger.error(f"Error getting cart for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def add_to_cart(self, user: User, product_id: str, quantity: int = 1) -> ServiceResult[Dict]:
        """
        Add item to cart (with stock validation).

        Args:
            user: User adding the item
            product_id: Product UUID
            quantity: Quantity to add (default: 1)

        Returns:
            ServiceResult with updated cart data

        Example:
            >>> result = cart_service.add_to_cart(user, product_id, quantity=2)
            >>> if result.ok:
            ...     cart_data = result.value
        """
        try:
            if quantity <= 0:
                return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity must be positive")

            # Get or create cart
            cart, _ = Cart.objects.get_or_create(user=user)

            # Get product
            try:
                product = Product.objects.select_for_update().get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found or inactive")

            # Check stock availability
            stock_check = self.inventory_service.check_availability(product_id, quantity)
            if not stock_check.ok:
                return stock_check

            if not stock_check.value:
                return service_err(
                    ErrorCodes.INSUFFICIENT_STOCK,
                    f"Insufficient stock for {product.name}. Available: {product.stock_quantity}",
                )

            # Add or update cart item
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart, product=product, defaults={"quantity": quantity}
            )

            if not created:
                # Item already in cart, update quantity
                new_quantity = cart_item.quantity + quantity

                # Validate new quantity against stock
                stock_check = self.inventory_service.check_availability(product_id, new_quantity)
                if not stock_check.ok or not stock_check.value:
                    return service_err(
                        ErrorCodes.INSUFFICIENT_STOCK,
                        f"Cannot add {quantity} more. Cart has {cart_item.quantity}, stock: {product.stock_quantity}",
                    )

                cart_item.quantity = new_quantity
                cart_item.save(update_fields=["quantity"])

                self.logger.info(
                    f"Updated cart item for user {user.id}: {product.name} quantity {cart_item.quantity - quantity} -> {cart_item.quantity}"
                )
            else:
                self.logger.info(f"Added to cart for user {user.id}: {quantity}x {product.name}")

            # Return updated cart
            return self.get_cart(user)

        except Exception as e:
            self.logger.error(f"Error adding to cart for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def remove_from_cart(self, user: User, product_id: str) -> ServiceResult[Dict]:
        """
        Remove item from cart.

        Args:
            user: User removing the item
            product_id: Product UUID to remove

        Returns:
            ServiceResult with updated cart data

        Example:
            >>> result = cart_service.remove_from_cart(user, product_id)
            >>> if result.ok:
            ...     cart_data = result.value
        """
        try:
            # Get cart
            try:
                cart = Cart.objects.get(user=user)
            except Cart.DoesNotExist:
                return service_err(ErrorCodes.CART_NOT_FOUND, "Cart not found")

            # Remove item
            try:
                cart_item = CartItem.objects.get(cart=cart, product_id=product_id)
                product_name = cart_item.product.name
                cart_item.delete()

                self.logger.info(f"Removed from cart for user {user.id}: {product_name}")

            except CartItem.DoesNotExist:
                return service_err(ErrorCodes.ITEM_NOT_IN_CART, f"Product {product_id} not in cart")

            # Return updated cart
            return self.get_cart(user)

        except Exception as e:
            self.logger.error(f"Error removing from cart for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def update_quantity(self, user: User, product_id: str, quantity: int) -> ServiceResult[Dict]:
        """
        Update quantity of item in cart.

        Args:
            user: User updating the quantity
            product_id: Product UUID
            quantity: New quantity (must be > 0)

        Returns:
            ServiceResult with updated cart data

        Example:
            >>> result = cart_service.update_quantity(user, product_id, quantity=5)
            >>> if result.ok:
            ...     cart_data = result.value
        """
        try:
            if quantity <= 0:
                return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity must be positive")

            # Get cart
            try:
                cart = Cart.objects.get(user=user)
            except Cart.DoesNotExist:
                return service_err(ErrorCodes.CART_NOT_FOUND, "Cart not found")

            # Get cart item
            try:
                cart_item = CartItem.objects.select_related("product").get(cart=cart, product_id=product_id)
            except CartItem.DoesNotExist:
                return service_err(ErrorCodes.ITEM_NOT_IN_CART, f"Product {product_id} not in cart")

            # Validate stock availability for new quantity
            stock_check = self.inventory_service.check_availability(product_id, quantity)
            if not stock_check.ok:
                return stock_check

            if not stock_check.value:
                return service_err(
                    ErrorCodes.INSUFFICIENT_STOCK,
                    f"Insufficient stock. Requested: {quantity}, Available: {cart_item.product.stock_quantity}",
                )

            # Update quantity
            old_quantity = cart_item.quantity
            cart_item.quantity = quantity
            cart_item.save(update_fields=["quantity"])

            self.logger.info(
                f"Updated cart quantity for user {user.id}: {cart_item.product.name} {old_quantity} -> {quantity}"
            )

            # Return updated cart
            return self.get_cart(user)

        except Exception as e:
            self.logger.error(f"Error updating cart quantity for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def clear_cart(self, user: User) -> ServiceResult[bool]:
        """
        Clear all items from cart.

        Args:
            user: User whose cart to clear

        Returns:
            ServiceResult with True if cleared

        Example:
            >>> result = cart_service.clear_cart(user)
            >>> if result.ok:
            ...     print("Cart cleared")
        """
        try:
            # Get cart
            try:
                cart = Cart.objects.get(user=user)
            except Cart.DoesNotExist:
                # Cart doesn't exist, nothing to clear
                return service_ok(True)

            # Clear items
            items_count = cart.items.count()
            cart.items.all().delete()

            self.logger.info(f"Cleared cart for user {user.id}: {items_count} items removed")

            return service_ok(True)

        except Exception as e:
            self.logger.error(f"Error clearing cart for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def validate_cart(self, user: User) -> ServiceResult[Dict]:
        """
        Validate cart items (check stock availability, active products, etc.).

        Returns validation status and any issues found.

        Args:
            user: User whose cart to validate

        Returns:
            ServiceResult with validation details

        Example:
            >>> result = cart_service.validate_cart(user)
            >>> if result.ok:
            ...     validation = result.value
            ...     if not validation["valid"]:
            ...         print("Issues:", validation["issues"])
        """
        try:
            cart_result = self.get_cart(user)
            if not cart_result.ok:
                return cart_result

            cart_data = cart_result.value
            items = cart_data["items"]

            issues = []
            valid = True

            validation_items = []
            for item in items:
                product = item["product"]
                quantity = item["quantity"]
                item_issues = []

                # Check if product is still active
                if not product.is_active:
                    issues.append(
                        {
                            "product_id": str(product.id),
                            "product_name": product.name,
                            "issue": "product_inactive",
                            "message": f"{product.name} is no longer available",
                        }
                    )
                    item_issues.append("Product inactive")
                    valid = False
                    # continue - Don't continue, still add to validation_items

                # Check stock availability
                stock_check = self.inventory_service.check_availability(str(product.id), quantity)
                if not stock_check.ok:
                    # If the stock service itself returned an error, propagate it immediately
                    return service_err(stock_check.error, stock_check.error_detail)

                if not stock_check.value:
                    issues.append(
                        {
                            "product_id": str(product.id),
                            "product_name": product.name,
                            "issue": "insufficient_stock",
                            "message": f"{product.name}: requested {quantity}, available {product.stock_quantity}",
                            "requested": quantity,
                            "available": product.stock_quantity,
                        }
                    )
                    item_issues.append(
                        f"Insufficient stock. Requested: {quantity}, available {product.stock_quantity}"
                    )
                    valid = False

                validation_items.append(
                    {
                        "product_id": str(product.id),
                        "product_name": product.name,
                        "quantity": quantity,
                        "available": product.stock_quantity,
                        "issues": item_issues,
                    }
                )

            validation = {
                "valid": valid,
                "issues": issues,
                "items": validation_items,  # Added items list
                "items_count": len(items),
                "total_items": len(items),  # For compatibility with legacy tests
                "checked_at": None,  # TODO: Add timestamp
            }

            self.logger.info(f"Validated cart for user {user.id}: valid={valid}, issues={len(issues)}")

            return service_ok(validation)

        except Exception as e:
            self.logger.error(f"Error validating cart for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
