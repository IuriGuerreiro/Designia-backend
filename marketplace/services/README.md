# Marketplace Service Layer

**Version:** 1.0.0
**Epic:** Epic 2 - Marketplace Service Layer Foundation
**Status:** ✅ Complete

---

## Overview

The Marketplace Service Layer provides a clean, testable business logic layer following SOLID principles. All services use the ServiceResult pattern for explicit error handling and support feature flags for gradual rollout.

### Architecture Principles

1. **Single Responsibility**: Each service handles one domain (products, cart, orders, etc.)
2. **Dependency Injection**: Services receive dependencies via constructor
3. **ServiceResult Pattern**: Explicit error handling without exceptions
4. **Feature Flags**: Gradual rollout with instant rollback capability
5. **Atomic Operations**: Database transactions for consistency
6. **Performance**: Caching, query optimization, async operations

---

## Services

### BaseService

**File:** `base.py`
**Lines:** 270

Foundation for all services. Provides:
- ServiceResult[T] pattern for error handling
- Error code constants
- Performance logging decorator
- Exception wrapping utilities

**Example:**
```python
from marketplace.services import CatalogService, service_ok, service_err

result = catalog_service.get_product(product_id)
if result.ok:
    product = result.value
    return Response({"product": product}, 200)
else:
    return Response({"error": result.error}, 400)
```

### CatalogService

**File:** `catalog_service.py`
**Lines:** 491

Product CRUD operations and browsing.

**Methods:**
- `list_products(filters, page, page_size, ordering)` - Product listing with pagination
- `get_product(product_id, track_view)` - Product detail
- `create_product(data, user, images)` - Create product (seller only)
- `update_product(product_id, data, user)` - Update product (owner only)
- `delete_product(product_id, user, hard_delete)` - Delete product
- `search_products(query, filters, limit)` - Basic search

**Features:**
- Storage abstraction integration for S3 uploads
- Ownership validation
- Soft delete support
- Query optimization (select_related, prefetch_related)

**Example:**
```python
from marketplace.services import CatalogService

catalog_service = CatalogService()
result = catalog_service.list_products(
    filters={"category": "electronics", "in_stock": True},
    page=1,
    page_size=20,
    ordering="-created_at"
)

if result.ok:
    products = result.value["results"]
    total = result.value["count"]
```

### CartService

**File:** `cart_service.py`
**Lines:** 412

Shopping cart operations with stock validation.

**Methods:**
- `get_cart(user)` - Get cart with items and totals
- `add_to_cart(user, product_id, quantity)` - Add with stock validation
- `remove_from_cart(user, product_id)` - Remove item
- `update_quantity(user, product_id, quantity)` - Update quantity
- `clear_cart(user)` - Clear all items
- `validate_cart(user)` - Validate before checkout

**Dependencies:**
- InventoryService (stock validation)
- PricingService (total calculations)

**Example:**
```python
from marketplace.services import CartService

cart_service = CartService()
result = cart_service.add_to_cart(user, product_id, quantity=2)

if result.ok:
    cart = result.value
    print(f"Cart total: ${cart['totals']['total']}")
```

### OrderService

**File:** `order_service.py`
**Lines:** 502

Complete order lifecycle management.

**Methods:**
- `create_order(user, shipping_address, notes, shipping_cost)` - Create from cart
- `get_order(order_id, user)` - Get order details
- `list_orders(user, status, page, page_size)` - List orders
- `update_shipping(order_id, tracking_number, carrier)` - Update shipping
- `cancel_order(order_id, user, reason)` - Cancel with inventory release
- `confirm_payment(order_id)` - Confirm payment (webhook)

**Dependencies:**
- CartService (cart validation)
- InventoryService (stock reservation)
- PricingService (totals calculation)

**Features:**
- Multi-step order creation with rollback
- Atomic inventory reservations
- Order state machine
- OrderItem snapshots (price, name at order time)

**Example:**
```python
from marketplace.services import OrderService

order_service = OrderService()
result = order_service.create_order(
    user=user,
    shipping_address={
        "name": "John Doe",
        "street": "123 Main St",
        "city": "Lisbon",
        "postal_code": "1000-001",
        "country": "Portugal"
    }
)

if result.ok:
    order = result.value
    print(f"Order {order.id} created: ${order.total_amount}")
```

### InventoryService

**File:** `inventory_service.py`
**Lines:** 335

Stock management with atomic operations.

**Methods:**
- `check_availability(product_id, quantity)` - Check stock
- `reserve_stock(product_id, quantity, order_id, user_id)` - Reserve (atomic)
- `release_stock(product_id, quantity, reason)` - Release reservation
- `update_stock(product_id, quantity, operation)` - Update (set/add/subtract)
- `is_in_stock(product_id)` - Simple check
- `get_stock_level(product_id)` - Get current quantity

**Features:**
- Database locking (`select_for_update()`) prevents race conditions
- Reservation tracking for audit trail
- Prevents negative stock
- Supports rollback operations

**Example:**
```python
from marketplace.services import InventoryService

inventory_service = InventoryService()

# Check availability
result = inventory_service.check_availability(product_id, quantity=5)
if result.ok and result.value:
    # Reserve stock
    reserve_result = inventory_service.reserve_stock(
        product_id, quantity=5, order_id=order_id
    )
```

### PricingService

**File:** `pricing_service.py`
**Lines:** 360

Price calculations with Decimal precision.

**Methods:**
- `calculate_product_price(product)` - Product pricing breakdown
- `calculate_discount_percentage(product)` - Discount %
- `is_on_sale(product)` - Sale status
- `calculate_cart_total(cart_items, region)` - Cart total with tax
- `calculate_order_total(items, shipping, region, coupon)` - Order total
- `calculate_shipping_cost(weight, distance)` - Shipping cost
- `validate_coupon(code, total)` - Coupon validation

**Features:**
- Decimal precision (no floating-point errors)
- Regional tax rates
- Coupon discount support
- Stateless methods (pure functions)

**Example:**
```python
from marketplace.services import PricingService

pricing_service = PricingService()

# Calculate cart total
result = pricing_service.calculate_cart_total(
    cart_items=[
        {"product": product1, "quantity": 2},
        {"product": product2, "quantity": 1}
    ],
    region="PT"
)

if result.ok:
    totals = result.value
    print(f"Subtotal: ${totals['subtotal']}")
    print(f"Tax: ${totals['tax']}")
    print(f"Total: ${totals['total']}")
```

### ReviewMetricsService

**File:** `review_metrics_service.py`
**Lines:** 348

Review aggregations with caching.

**Methods:**
- `calculate_average_rating(product_id, use_cache)` - Average rating
- `get_rating_distribution(product_id, use_cache)` - Star breakdown (1-5)
- `get_review_count(product_id, use_cache)` - Total reviews
- `update_metrics(product_id)` - Refresh all metrics
- `get_top_reviews(product_id, limit)` - Top reviews
- `get_all_metrics(product_id, use_cache)` - All metrics in one call
- `invalidate_cache(product_id)` - Clear cache

**Features:**
- Django cache integration (1 hour default)
- Cache invalidation on review changes
- Decimal precision for ratings
- Verified purchase prioritization

**Example:**
```python
from marketplace.services import ReviewMetricsService

review_metrics_service = ReviewMetricsService()

# Get all metrics
result = review_metrics_service.get_all_metrics(product_id)
if result.ok:
    metrics = result.value
    print(f"Average: {metrics['average_rating']}")
    print(f"Total Reviews: {metrics['review_count']}")
    print(f"Distribution: {metrics['rating_distribution']}")
```

### SearchService

**File:** `search_service.py`
**Lines:** 461

Advanced product search and filtering.

**Methods:**
- `search(query, filters, sort, page, page_size)` - Full-text search
- `autocomplete(query, limit)` - Autocomplete suggestions
- `get_suggestions(query, limit)` - Related search terms
- `filter_products(filters, page, page_size, sort)` - Filter without search
- `get_trending_products(limit, timeframe_days)` - Trending products
- `get_related_products(product_id, limit)` - Related products

**Features:**
- PostgreSQL full-text search with ranking
- Fallback ILIKE search for non-Postgres
- Advanced filtering (category, price, rating, stock, brand)
- Multiple sort options (relevance, price, rating, newest)
- Performance-optimized

**Example:**
```python
from marketplace.services import SearchService

search_service = SearchService()

# Full-text search
result = search_service.search(
    query="iPhone",
    filters={"category": "electronics", "price_min": 500, "in_stock": True},
    sort="price_asc",
    page=1,
    page_size=20
)

if result.ok:
    products = result.value["results"]
    total = result.value["count"]

# Autocomplete
autocomplete_result = search_service.autocomplete("iPh", limit=5)
if autocomplete_result.ok:
    suggestions = autocomplete_result.value
```

---

## ServiceResult Pattern

All services return `ServiceResult[T]` for explicit error handling.

### Structure

```python
@dataclass
class ServiceResult(Generic[T]):
    ok: bool
    value: Optional[T] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None
```

### Usage

```python
# Success case
result = service.do_something(params)
if result.ok:
    data = result.value
    # Process success
else:
    error_code = result.error
    error_message = result.error_detail
    # Handle error
```

### Helper Functions

```python
# Create success result
service_ok(value)

# Create error result
service_err(error_code, detail_message)
```

### Chaining Operations

```python
# Map: Transform success value
result.map(lambda x: x * 2)

# FlatMap: Chain operations
result.flat_map(lambda x: another_service.process(x))

# To Dict: JSON serialization
result.to_dict()
```

---

## Error Codes

Standard error codes defined in `ErrorCodes` class:

### General
- `INTERNAL_ERROR` - Unexpected server error
- `VALIDATION_ERROR` - Input validation failed
- `INVALID_INPUT` - Invalid input parameters

### Products
- `PRODUCT_NOT_FOUND` - Product doesn't exist
- `NOT_PRODUCT_OWNER` - User doesn't own product
- `PERMISSION_DENIED` - Permission denied

### Inventory
- `INSUFFICIENT_STOCK` - Not enough stock
- `INVALID_QUANTITY` - Invalid quantity (negative, zero)
- `RESERVATION_FAILED` - Stock reservation failed

### Cart
- `CART_NOT_FOUND` - Cart doesn't exist
- `CART_EMPTY` - Cart has no items
- `ITEM_NOT_IN_CART` - Item not in cart

### Orders
- `ORDER_NOT_FOUND` - Order doesn't exist
- `NOT_ORDER_OWNER` - User doesn't own order
- `INVALID_ORDER_STATE` - Invalid state transition
- `ORDER_CANNOT_CANCEL` - Order can't be cancelled

---

## Feature Flags

Enable/disable services via environment variables.

### Available Flags

```python
# In settings.py
FEATURE_FLAGS = {
    "USE_SERVICE_LAYER_MARKETPLACE": env("FEATURE_FLAG_USE_SERVICE_LAYER_MARKETPLACE", default=False),
    "USE_SERVICE_LAYER_PRODUCTS": env("FEATURE_FLAG_USE_SERVICE_LAYER_PRODUCTS", default=False),
    "USE_SERVICE_LAYER_CART": env("FEATURE_FLAG_USE_SERVICE_LAYER_CART", default=False),
    "USE_SERVICE_LAYER_ORDERS": env("FEATURE_FLAG_USE_SERVICE_LAYER_ORDERS", default=False),
}
```

### Usage in Views

```python
from django.conf import settings

def list(self, request):
    if settings.FEATURE_FLAGS.get("USE_SERVICE_LAYER_PRODUCTS", False):
        # Use service layer
        return self._list_via_service(request)
    else:
        # Use legacy implementation
        return self._list_legacy(request)
```

### Environment Variables

```bash
# Enable product service layer
export FEATURE_FLAG_USE_SERVICE_LAYER_PRODUCTS=true

# Disable (rollback)
export FEATURE_FLAG_USE_SERVICE_LAYER_PRODUCTS=false
```

---

## Testing

### Unit Tests

Test services in isolation with mocked dependencies.

```python
from marketplace.services import CartService, InventoryService, PricingService
from unittest.mock import Mock

def test_add_to_cart_success():
    # Mock dependencies
    inventory_service = Mock(spec=InventoryService)
    inventory_service.check_availability.return_value = service_ok(True)

    pricing_service = Mock(spec=PricingService)

    # Create service with mocks
    cart_service = CartService(
        inventory_service=inventory_service,
        pricing_service=pricing_service
    )

    # Test
    result = cart_service.add_to_cart(user, product_id, quantity=2)
    assert result.ok
    assert result.value is not None
```

### Integration Tests

Test services with real database.

```python
from django.test import TransactionTestCase
from marketplace.services import OrderService

class OrderServiceIntegrationTest(TransactionTestCase):
    def test_create_order_full_flow(self):
        # Setup: Create user, products, add to cart
        user = User.objects.create(...)
        product = Product.objects.create(...)
        cart_service.add_to_cart(user, product.id, quantity=1)

        # Test: Create order
        order_service = OrderService()
        result = order_service.create_order(user, shipping_address={...})

        # Verify
        self.assertTrue(result.ok)
        order = result.value
        self.assertEqual(order.status, "pending_payment")

        # Verify inventory was reserved
        product.refresh_from_database()
        self.assertEqual(product.stock_quantity, 9)  # Was 10
```

---

## Migration Guide

### Migrating Views to Service Layer

**Step 1:** Enable feature flag in `.env`
```bash
FEATURE_FLAG_USE_SERVICE_LAYER_PRODUCTS=true
```

**Step 2:** Add feature flag routing in view
```python
def list(self, request):
    from django.conf import settings

    if settings.FEATURE_FLAGS.get("USE_SERVICE_LAYER_PRODUCTS", False):
        return self._list_via_service(request)
    else:
        return self._list_legacy(request)
```

**Step 3:** Implement service-based method
```python
def _list_via_service(self, request):
    from marketplace.services import CatalogService

    # Extract filters from request
    filters = {
        "category": request.query_params.get("category"),
        "in_stock": True
    }

    # Call service
    catalog_service = CatalogService()
    result = catalog_service.list_products(filters=filters)

    if not result.ok:
        return Response({"error": result.error}, 500)

    # Serialize and return
    serializer = self.get_serializer(result.value["results"], many=True)
    return Response(serializer.data)
```

**Step 4:** Test in production with flag enabled

**Step 5:** Monitor logs for errors

**Step 6:** Rollback if needed (set flag to false)

**Step 7:** Once stable, remove legacy code

---

## Performance Considerations

### Database Optimization

1. **Query Optimization**
   - All services use `select_related()` for foreign keys
   - All services use `prefetch_related()` for reverse relations
   - Annotate aggregates to avoid N+1 queries

2. **Database Locking**
   - InventoryService uses `select_for_update()` for atomic operations
   - OrderService uses transactions for multi-step operations

3. **Caching**
   - ReviewMetricsService caches expensive aggregations
   - Cache timeout: 1 hour (configurable)
   - Cache invalidation on review changes

### Async Operations

Some operations are delegated to background tasks:
- View tracking (ProductViewSet.list)
- Metrics initialization (product creation)
- Email notifications (order creation)

---

## Logging

All services use structured logging.

### Log Levels

- **INFO**: Normal operations (product created, cart updated)
- **WARNING**: Non-critical issues (cache miss, failed image upload)
- **ERROR**: Errors requiring attention (stock reservation failed)

### Example Logs

```
INFO marketplace.services.catalog_service: Created product: iPhone 15 (id=abc123) by seller 456
INFO marketplace.services.order_service: Created order def789 for user 123: 3 items, total $999.00
ERROR marketplace.services.inventory_service: Failed to reserve stock for product abc123: insufficient stock
```

### Performance Logging

Services automatically log method execution time:

```python
@BaseService.log_performance
def create_order(...):
    # Implementation
```

Log output:
```
INFO marketplace.services.order_service: create_order completed in 245.3ms
```

---

## Dependencies

### Service Dependencies

```
OrderService
├── CartService
│   ├── InventoryService
│   └── PricingService
├── InventoryService
└── PricingService

CatalogService
└── (storage container)

ReviewMetricsService
└── (Django cache)

SearchService
└── (none - stateless)
```

### External Dependencies

- **Django ORM**: Database operations
- **Django Cache**: ReviewMetricsService caching
- **Infrastructure Container**: Storage abstraction (S3 uploads)
- **Decimal**: Financial calculations

---

## Future Enhancements

### Epic 3: View Refactoring
- Migrate all remaining views to use services
- Remove legacy implementations after testing

### Epic 4: Payment System
- PaymentService for Stripe integration
- RefundService for refund processing
- PaymentWebhookService for webhook handling

### Epic 5: Model Decomposition
- Break down large models (User, Product)
- Create dedicated models for addresses, phone numbers
- Improve database normalization

### Epic 6: Testing & Quality
- Achieve 80%+ test coverage
- Add integration tests for all services
- Performance benchmarking
- Load testing for order creation

---

## Support

For questions or issues:

1. Check service docstrings in source code
2. Review example usage in this README
3. Check implementation progress: `docs/implementation-progress.md`
4. Review epic breakdown: `docs/epics.md`

---

**Last Updated:** 2025-11-30
**Epic Status:** ✅ Complete (10/10 stories)
**Total Lines of Code:** 3,640 lines across 8 service files
