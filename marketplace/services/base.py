"""
Base classes and utilities for the service layer.

This module provides the ServiceResult pattern (inspired by Rust's Result type)
and BaseService class for all marketplace services.

Story 2.1: ServiceResult Pattern & Base Classes
"""

import logging
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ServiceResult(Generic[T]):
    """
    A result type that encapsulates success or failure from service operations.

    Inspired by Rust's Result<T, E> type, this provides a clean way to handle
    service operation outcomes without exceptions for expected failures.

    Attributes:
        ok: True if operation succeeded, False otherwise
        value: The success value (present if ok=True)
        error: Error code (present if ok=False)
        error_detail: Human-readable error message (present if ok=False)

    Examples:
        >>> result = service_ok(product)
        >>> if result.ok:
        ...     return Response({"product": result.value}, 200)
        >>> else:
        ...     return Response({"error": result.error}, 400)

        >>> result = service_err("product_not_found", "Product with ID 123 does not exist")
        >>> print(result.error)  # "product_not_found"
        >>> print(result.error_detail)  # "Product with ID 123 does not exist"
    """

    ok: bool
    value: Optional[T] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None

    def map(self, func: Callable[[T], Any]) -> "ServiceResult":
        """
        Transform the success value if ok=True, otherwise pass through error.

        Args:
            func: Function to apply to the value

        Returns:
            ServiceResult with transformed value or original error
        """
        if self.ok and self.value is not None:
            try:
                return service_ok(func(self.value))
            except Exception as e:
                return service_err("transformation_error", str(e))
        return self

    def flat_map(self, func: Callable[[T], "ServiceResult"]) -> "ServiceResult":
        """
        Chain service operations that return ServiceResult.

        Args:
            func: Function that takes value and returns ServiceResult

        Returns:
            Result from func if ok=True, otherwise original error
        """
        if self.ok and self.value is not None:
            return func(self.value)
        return self

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with 'success' and either 'data' or 'error'
        """
        if self.ok:
            return {"success": True, "data": self.value}
        return {
            "success": False,
            "error": {"code": self.error, "message": self.error_detail},
        }


def service_ok(value: T) -> ServiceResult[T]:
    """
    Create a successful ServiceResult.

    Args:
        value: The success value

    Returns:
        ServiceResult with ok=True and the value

    Example:
        >>> product = Product.objects.get(id=123)
        >>> return service_ok(product)
    """
    return ServiceResult(ok=True, value=value)


def service_err(error: str, error_detail: str = "") -> ServiceResult:
    """
    Create a failed ServiceResult.

    Args:
        error: Error code (e.g., "product_not_found", "invalid_quantity")
        error_detail: Human-readable error message

    Returns:
        ServiceResult with ok=False and error information

    Example:
        >>> return service_err("product_not_found", f"Product {id} does not exist")
    """
    return ServiceResult(ok=False, error=error, error_detail=error_detail or error)


class BaseService:
    """
    Base class for all services providing common functionality.

    Provides:
    - Logging with class name
    - Performance timing decorator
    - Error handling utilities

    Usage:
        class CatalogService(BaseService):
            def __init__(self, storage):
                super().__init__()
                self.storage = storage

            @BaseService.log_performance
            def list_products(self, filters):
                self.logger.info(f"Listing products with filters: {filters}")
                # ... implementation
    """

    def __init__(self):
        """Initialize base service with logger."""
        self.logger = logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)

    @staticmethod
    def log_performance(func: Callable) -> Callable:
        """
        Decorator to log performance of service methods.

        Logs execution time and any errors that occur.

        Args:
            func: The service method to wrap

        Returns:
            Wrapped function with performance logging

        Example:
            @BaseService.log_performance
            def expensive_operation(self):
                # ... operation
        """

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            method_name = f"{self.__class__.__name__}.{func.__name__}"

            try:
                self.logger.debug(f"{method_name} started")
                result = func(self, *args, **kwargs)
                elapsed_time = (time.time() - start_time) * 1000  # Convert to ms

                # Log based on result type
                if isinstance(result, ServiceResult):
                    if result.ok:
                        self.logger.info(f"{method_name} completed successfully in {elapsed_time:.2f}ms")
                    else:
                        self.logger.warning(
                            f"{method_name} failed with error '{result.error}' in {elapsed_time:.2f}ms"
                        )
                else:
                    self.logger.info(f"{method_name} completed in {elapsed_time:.2f}ms")

                return result

            except Exception as e:
                elapsed_time = (time.time() - start_time) * 1000
                self.logger.error(
                    f"{method_name} raised exception after {elapsed_time:.2f}ms: {str(e)}",
                    exc_info=True,
                )
                raise

        return wrapper

    def wrap_exception(self, func: Callable, error_code: str = "internal_error") -> ServiceResult:
        """
        Execute a function and wrap any exception in a ServiceResult.

        Args:
            func: Function to execute
            error_code: Error code to use if exception occurs

        Returns:
            ServiceResult with function result or error

        Example:
            result = self.wrap_exception(
                lambda: Product.objects.get(id=product_id),
                error_code="product_not_found"
            )
        """
        try:
            value = func()
            return service_ok(value)
        except Exception as e:
            self.logger.error(f"Exception in {func.__name__}: {str(e)}", exc_info=True)
            return service_err(error_code, str(e))


# Common error codes for marketplace services
class ErrorCodes:
    """Standard error codes used across marketplace services."""

    # Product errors
    PRODUCT_NOT_FOUND = "product_not_found"
    PRODUCT_INACTIVE = "product_inactive"
    PRODUCT_OUT_OF_STOCK = "product_out_of_stock"
    INVALID_PRODUCT_DATA = "invalid_product_data"

    # Cart errors
    CART_NOT_FOUND = "cart_not_found"
    CART_EMPTY = "cart_empty"
    INVALID_QUANTITY = "invalid_quantity"
    ITEM_NOT_IN_CART = "item_not_in_cart"

    # Order errors
    ORDER_NOT_FOUND = "order_not_found"
    ORDER_ALREADY_PAID = "order_already_paid"
    ORDER_CANNOT_CANCEL = "order_cannot_cancel"
    INVALID_ORDER_STATE = "invalid_order_state"

    # Inventory errors
    INSUFFICIENT_STOCK = "insufficient_stock"
    RESERVATION_FAILED = "reservation_failed"
    RESERVATION_EXPIRED = "reservation_expired"

    # Permission errors
    PERMISSION_DENIED = "permission_denied"
    NOT_PRODUCT_OWNER = "not_product_owner"
    NOT_ORDER_OWNER = "not_order_owner"

    # Validation errors
    VALIDATION_ERROR = "validation_error"
    INVALID_INPUT = "invalid_input"

    # Internal errors
    INTERNAL_ERROR = "internal_error"
    DATABASE_ERROR = "database_error"
