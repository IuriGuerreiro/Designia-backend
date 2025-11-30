"""
Marketplace Service Layer

This package contains all business logic for the marketplace app, organized
into domain services following SOLID principles.

Services:
- CatalogService: Product browsing, search, and CRUD
- CartService: Shopping cart operations
- OrderService: Order lifecycle management
- InventoryService: Stock tracking and reservation
- PricingService: Price calculations and discounts
- ReviewMetricsService: Review aggregations and metrics
- SearchService: Product search and filtering

Usage:
    from marketplace.services import CatalogService, service_ok, service_err

    catalog_service = CatalogService(storage=container.storage())
    result = catalog_service.list_products(filters={})

    if result.ok:
        products = result.value
    else:
        error = result.error
"""

from .base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from .cart_service import CartService
from .catalog_service import CatalogService
from .inventory_service import InventoryService
from .order_service import OrderService
from .pricing_service import PricingService
from .review_metrics_service import ReviewMetricsService
from .search_service import SearchService

__all__ = [
    # Base classes
    "BaseService",
    "ServiceResult",
    # Helper functions
    "service_ok",
    "service_err",
    # Error codes
    "ErrorCodes",
    # Services (implemented)
    "CatalogService",
    "CartService",
    "InventoryService",
    "OrderService",
    "PricingService",
    "ReviewMetricsService",
    "SearchService",
]
