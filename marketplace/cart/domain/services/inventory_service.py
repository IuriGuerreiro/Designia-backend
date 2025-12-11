"""
InventoryService - Stock Management

Handles product inventory tracking, stock reservations, and availability checks.
Uses database-level locking to prevent race conditions and overselling.

Story 2.5: InventoryService - Stock Management
"""

import logging
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from marketplace.catalog.domain.models.catalog import Product
from marketplace.catalog.domain.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from marketplace.infra.observability.metrics import stock_reservation_failures

logger = logging.getLogger(__name__)


class InventoryService(BaseService):
    """
    Service for managing product inventory and stock reservations.
    """

    def __init__(self):
        """Initialize InventoryService."""
        super().__init__()
        self.reservation_timeout = getattr(settings, "INVENTORY_RESERVATION_TIMEOUT_MINUTES", 15)

    @BaseService.log_performance
    def check_availability(self, product_id: str, quantity: int = 1) -> ServiceResult[bool]:
        """
        Check if a product has sufficient stock available.

        Args:
            product_id: UUID of the product
            quantity: Quantity to check (default: 1)

        Returns:
            ServiceResult with True if available, False otherwise

        Example:
            >>> result = inventory_service.check_availability(product_id, 5)
            >>> if result.ok and result.value:
            ...     print("Product is in stock!")
        """
        if quantity <= 0:
            return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity must be positive")

        try:
            product = Product.objects.get(id=product_id, is_active=True)

            # Check if product has enough stock
            available = product.stock_quantity >= quantity

            self.logger.info(
                f"Availability check for product {product_id}: "
                f"requested={quantity}, available={product.stock_quantity}, result={available}"
            )

            return service_ok(available)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error checking availability for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def reserve_stock(
        self, product_id: str, quantity: int, order_id: Optional[str] = None, user_id: Optional[int] = None
    ) -> ServiceResult[dict]:
        """
        Reserve stock for an order or cart (atomic operation with database lock).

        This prevents overselling by using SELECT FOR UPDATE to lock the product row.

        Args:
            product_id: UUID of the product
            quantity: Quantity to reserve
            order_id: Optional order ID for tracking
            user_id: Optional user ID for tracking

        Returns:
            ServiceResult with reservation details or error:
            - quantity_reserved: Reserved amount
            - new_stock: Updated stock level
            - reserved_at: Timestamp
        """
        if quantity <= 0:
            return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity must be positive")

        try:
            # Lock the product row to prevent concurrent modifications
            product = Product.objects.select_for_update().get(id=product_id, is_active=True)

            # Check if sufficient stock available
            if product.stock_quantity < quantity:
                return service_err(
                    ErrorCodes.INSUFFICIENT_STOCK,
                    f"Insufficient stock for product {product.name}. "
                    f"Available: {product.stock_quantity}, Requested: {quantity}",
                )

            # Deduct stock
            old_quantity = product.stock_quantity
            product.stock_quantity -= quantity
            product.save(update_fields=["stock_quantity"])

            reservation_data = {
                "product_id": str(product_id),
                "product_name": product.name,
                "quantity_reserved": quantity,
                "old_stock": old_quantity,
                "new_stock": product.stock_quantity,
                "order_id": order_id,
                "user_id": user_id,
                "reserved_at": timezone.now().isoformat(),
            }

            self.logger.info(
                f"Stock reserved: product={product.name}, "
                f"quantity={quantity}, order={order_id}, "
                f"stock: {old_quantity} -> {product.stock_quantity}"
            )

            # TODO: Create InventoryReservation record for tracking (Story 5.3)
            # This will allow cleanup of expired reservations via Celery task

            return service_ok(reservation_data)

        except Product.DoesNotExist:
            stock_reservation_failures.inc()
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            stock_reservation_failures.inc()
            self.logger.error(f"Error reserving stock for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.RESERVATION_FAILED, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def release_stock(self, product_id: str, quantity: int, reason: str = "order_cancelled") -> ServiceResult[dict]:
        """
        Release reserved stock back to inventory (atomic operation).

        Used when orders are cancelled or reservations expire.

        Args:
            product_id: UUID of the product
            quantity: Quantity to release
            reason: Reason for release (for audit logging)

        Returns:
            ServiceResult with release details or error

        Example:
            >>> result = inventory_service.release_stock(product_id, 2, "order_cancelled")
            >>> if result.ok:
            ...     print(f"Released: {result.value}")
        """
        if quantity <= 0:
            return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity must be positive")

        try:
            # Lock the product row
            product = Product.objects.select_for_update().get(id=product_id)

            # Add stock back
            old_quantity = product.stock_quantity
            product.stock_quantity += quantity
            product.save(update_fields=["stock_quantity"])

            release_data = {
                "product_id": str(product_id),
                "product_name": product.name,
                "quantity_released": quantity,
                "old_stock": old_quantity,
                "new_stock": product.stock_quantity,
                "reason": reason,
                "released_at": timezone.now().isoformat(),
            }

            self.logger.info(
                f"Stock released: product={product.name}, "
                f"quantity={quantity}, reason={reason}, "
                f"stock: {old_quantity} -> {product.stock_quantity}"
            )

            return service_ok(release_data)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error releasing stock for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def update_stock(self, product_id: str, quantity: int, operation: str = "set") -> ServiceResult[dict]:
        """
        Update product stock quantity (admin operation).

        Args:
            product_id: UUID of the product
            quantity: Quantity value
            operation: 'set', 'add', or 'subtract'

        Returns:
            ServiceResult with update details or error

        Example:
            >>> # Set stock to 100
            >>> result = inventory_service.update_stock(product_id, 100, "set")
            >>> # Add 50 to current stock
            >>> result = inventory_service.update_stock(product_id, 50, "add")
        """
        if operation not in ["set", "add", "subtract"]:
            return service_err(ErrorCodes.INVALID_INPUT, "Operation must be 'set', 'add', or 'subtract'")

        try:
            # Lock the product row
            product = Product.objects.select_for_update().get(id=product_id)

            old_quantity = product.stock_quantity

            if operation == "set":
                if quantity < 0:
                    return service_err(ErrorCodes.INVALID_QUANTITY, "Stock quantity cannot be negative")
                product.stock_quantity = quantity
            elif operation == "add":
                if quantity <= 0:
                    return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity to add must be positive")
                product.stock_quantity += quantity
            elif operation == "subtract":
                if quantity <= 0:
                    return service_err(ErrorCodes.INVALID_QUANTITY, "Quantity to subtract must be positive")
                if product.stock_quantity < quantity:
                    return service_err(
                        ErrorCodes.INSUFFICIENT_STOCK,
                        f"Cannot subtract {quantity} from stock of {product.stock_quantity}",
                    )
                product.stock_quantity -= quantity

            product.save(update_fields=["stock_quantity"])

            update_data = {
                "product_id": str(product_id),
                "product_name": product.name,
                "operation": operation,
                "quantity": quantity,
                "old_stock": old_quantity,
                "new_stock": product.stock_quantity,
                "updated_at": timezone.now().isoformat(),
            }

            self.logger.info(
                f"Stock updated: product={product.name}, "
                f"operation={operation}, quantity={quantity}, "
                f"stock: {old_quantity} -> {product.stock_quantity}"
            )

            return service_ok(update_data)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error updating stock for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def is_in_stock(self, product_id: str) -> ServiceResult[bool]:
        """
        Check if product is in stock (quantity > 0).

        Args:
            product_id: UUID of the product

        Returns:
            ServiceResult with True if in stock, False otherwise

        Example:
            >>> result = inventory_service.is_in_stock(product_id)
            >>> if result.ok and result.value:
            ...     print("In stock!")
        """
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            return service_ok(product.stock_quantity > 0)
        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error checking stock for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def get_stock_level(self, product_id: str) -> ServiceResult[int]:
        """
        Get current stock quantity for a product.

        Args:
            product_id: UUID of the product

        Returns:
            ServiceResult with stock quantity

        Example:
            >>> result = inventory_service.get_stock_level(product_id)
            >>> if result.ok:
            ...     print(f"Stock: {result.value}")
        """
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            return service_ok(product.stock_quantity)
        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error getting stock level for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
