# Marketplace Services

This directory contains the Domain Services for the Marketplace application.

## Services

### `CatalogService`
Handles product retrieval, search, filtering, and category management.
- **Key Methods:** `search_products`, `get_product_detail`, `get_categories`

### `CartService`
Manages shopping cart operations.
- **Key Methods:** `get_cart`, `add_item`, `remove_item`, `update_quantity`, `clear_cart`
- **Dependencies:** `InventoryService` (availability), `PricingService` (totals)

### `OrderService`
Manages order lifecycle from creation to completion.
- **Key Methods:** `create_order_from_cart`, `get_order_detail`, `cancel_order`
- **Dependencies:** `CartService`, `InventoryService`, `PricingService`, `PaymentService`

### `PricingService`
Centralized pricing logic.
- **Key Methods:** `calculate_product_price`, `calculate_cart_total`, `is_on_sale`
- **Notes:** Handles tax and currency logic.

### `InventoryService`
Manages stock levels and reservations.
- **Key Methods:** `check_availability`, `reserve_stock`, `release_stock`, `is_in_stock`
- **Notes:** Uses database locks for atomicity.

### `ReviewMetricsService`
Handles product reviews and ratings.
- **Key Methods:** `calculate_average_rating`, `get_review_count`, `get_rating_distribution`
- **Notes:** Uses caching for performance.

### `SearchService`
Advanced search functionality (if separate from CatalogService).
- **Key Methods:** `search`

## Usage

Import services directly in views or other services:

```python
from marketplace.services.catalog_service import CatalogService

def my_view(request):
    products = CatalogService().search_products(query="shoes")
    # ...
```
