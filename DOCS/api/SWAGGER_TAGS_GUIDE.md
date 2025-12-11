# Swagger UI - Tags & Organization Guide

**How to organize endpoints in Swagger UI using tags**

---

## 🎯 What Are Swagger Tags?

Tags in Swagger/OpenAPI group related endpoints together in the documentation UI. They create collapsible sections that organize your API logically.

**Example in Swagger UI:**
```
📂 Products
  ├── GET  /api/marketplace/products/
  ├── POST /api/marketplace/products/
  └── GET  /api/marketplace/products/{slug}/

📂 Cart
  ├── GET  /api/marketplace/cart/
  ├── POST /api/marketplace/cart/add/
  └── GET  /api/marketplace/cart/validate/

📂 Orders
  ├── GET  /api/marketplace/orders/
  └── POST /api/marketplace/orders/
```

---

## 📋 Marketplace API Tag Structure

### Current Tag Organization

```
1. Categories
   - Category listing and details

2. Products
   - Product CRUD operations
   - Product listing with filters

3. Products > Search
   - Search products
   - Autocomplete
   - Get filters

4. Products > Reviews
   - List/Create/Update/Delete reviews (nested under products)

5. Products > Images
   - Manage product images (nested under products)

6. Products > Metrics
   - Product analytics and metrics

7. Cart
   - Cart operations (get, add, update, remove, validate)

8. Orders
   - Order lifecycle (list, create, get, cancel)

9. Sellers
   - Seller profiles and products

10. User Profiles
    - User profile management

11. Internal APIs
    - Service-to-service endpoints

12. Monitoring
    - Prometheus metrics
```

---

## 🛠️ How to Add Tags to Views

### For ViewSets (Most Common)

Use `@extend_schema_view` decorator at the class level:

```python
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import viewsets

@extend_schema_view(
    list=extend_schema(
        summary="List all products",
        description="Get a paginated list of products with filtering options",
        tags=["Products"],
    ),
    retrieve=extend_schema(
        summary="Get product details",
        description="Retrieve detailed information about a specific product",
        tags=["Products"],
    ),
    create=extend_schema(
        summary="Create a new product",
        description="Create a new product listing (seller only)",
        tags=["Products"],
    ),
    update=extend_schema(
        summary="Update product",
        description="Update an existing product (owner only)",
        tags=["Products"],
    ),
    destroy=extend_schema(
        summary="Delete product",
        description="Delete a product (owner only)",
        tags=["Products"],
    ),
)
class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for products with full CRUD operations.
    """
    # ... your view implementation
```

### For Custom Actions on ViewSets

Use `@extend_schema` decorator on the method:

```python
from rest_framework.decorators import action

class ProductViewSet(viewsets.ModelViewSet):

    @extend_schema(
        summary="Get product metrics",
        description="Get analytics and metrics for a specific product",
        tags=["Products > Metrics"],
    )
    @action(detail=True, methods=["get"])
    def metrics(self, request, slug=None):
        # Your implementation
        pass
```

### For Function-Based Views

Use `@extend_schema` decorator directly:

```python
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view

@extend_schema(
    operation_id="get_seller_profile",
    summary="Get seller profile",
    description="Retrieve public seller profile information",
    tags=["Sellers"],
)
@api_view(["GET"])
def seller_profile(request, seller_id):
    # Your implementation
    pass
```

### For ViewSet Views (Non-ModelViewSet)

```python
@extend_schema_view(
    list=extend_schema(
        summary="List reviews for a product",
        description="Get all reviews for a specific product",
        tags=["Products > Reviews"],
    ),
    create=extend_schema(
        summary="Create a review",
        description="Write a review for a product (requires purchase)",
        tags=["Products > Reviews"],
    ),
)
class ReviewViewSet(viewsets.ViewSet):
    # Your implementation
    pass
```

---

## 📝 Complete Examples by Resource

### 1. Products ViewSet

```python
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import viewsets, status

@extend_schema_view(
    list=extend_schema(
        operation_id="list_products",
        summary="List all products",
        description="""
        Get a paginated list of products with filtering options.

        **Filters Available:**
        - category: Filter by category slug
        - price_min/max: Price range filter
        - brand: Filter by brand name
        - in_stock: Show only in-stock items
        - condition: Product condition

        **Sorting:**
        - Use 'ordering' parameter: -created_at, price, -price, -view_count
        """,
        parameters=[
            OpenApiParameter("page", type=int, description="Page number"),
            OpenApiParameter("page_size", type=int, description="Items per page"),
            OpenApiParameter("category", type=str, description="Category slug"),
            OpenApiParameter("price_min", type=float, description="Minimum price"),
            OpenApiParameter("price_max", type=float, description="Maximum price"),
            OpenApiParameter("brand", type=str, description="Brand name"),
            OpenApiParameter("in_stock", type=bool, description="In stock only"),
            OpenApiParameter("ordering", type=str, description="Sort order"),
        ],
        tags=["Products"],
    ),
    retrieve=extend_schema(
        operation_id="get_product",
        summary="Get product details",
        description="Retrieve detailed information about a specific product. View count is incremented.",
        tags=["Products"],
    ),
    create=extend_schema(
        operation_id="create_product",
        summary="Create a new product",
        description="""
        Create a new product listing.

        **Requires:** Verified seller account
        **Receives:** Product data with optional images
        **Returns:** Created product with generated slug
        """,
        tags=["Products"],
    ),
    update=extend_schema(
        operation_id="update_product",
        summary="Update product",
        description="Update an existing product. Only the product owner can update.",
        tags=["Products"],
    ),
    partial_update=extend_schema(
        operation_id="partial_update_product",
        summary="Partially update product",
        description="Update specific fields of a product.",
        tags=["Products"],
    ),
    destroy=extend_schema(
        operation_id="delete_product",
        summary="Delete product",
        description="Delete a product (soft delete). Only the owner can delete.",
        tags=["Products"],
    ),
)
class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet for products with full CRUD operations."""
    pass
```

### 2. Cart ViewSet

```python
@extend_schema_view(
    list=extend_schema(
        operation_id="get_cart",
        summary="Get user's shopping cart",
        description="""
        Retrieve the current user's cart with items and totals.

        **Returns:**
        - List of cart items with product details
        - Cart totals (subtotal, shipping, tax, total)
        - Item count
        """,
        tags=["Cart"],
    ),
)
class CartViewSet(viewsets.ViewSet):
    """ViewSet for shopping cart operations."""

    @extend_schema(
        operation_id="add_to_cart",
        summary="Add item to cart",
        description="""
        Add a product to the shopping cart.

        **Receives:** product_id (UUID), quantity (integer)
        **Returns:** Updated cart
        **Rate Limited:** 60 requests/minute
        """,
        tags=["Cart"],
    )
    @action(detail=False, methods=["post"])
    def add(self, request):
        pass

    @extend_schema(
        operation_id="validate_cart",
        summary="Validate cart before checkout",
        description="""
        Check cart for issues:
        - Out of stock items
        - Inactive products
        - Price changes

        **Use before:** Creating an order
        """,
        tags=["Cart"],
    )
    @action(detail=False, methods=["get"])
    def validate(self, request):
        pass
```

### 3. Reviews ViewSet (Nested under Products)

```python
@extend_schema_view(
    list=extend_schema(
        operation_id="list_product_reviews",
        summary="List reviews for a product",
        description="""
        Get all reviews for a specific product.

        **URL:** /products/{slug}/reviews/
        **Pagination:** Supports page and page_size parameters
        """,
        tags=["Products > Reviews"],
    ),
    create=extend_schema(
        operation_id="create_product_review",
        summary="Create a review for a product",
        description="""
        Write a review for a product.

        **Requirements:**
        - Must have purchased the product
        - One review per product per user

        **Receives:** rating (1-5), title, comment
        """,
        tags=["Products > Reviews"],
    ),
    retrieve=extend_schema(
        operation_id="get_product_review",
        summary="Get a specific review",
        description="Retrieve details of a specific review",
        tags=["Products > Reviews"],
    ),
    update=extend_schema(
        operation_id="update_product_review",
        summary="Update your review",
        description="Update your own review (owner only)",
        tags=["Products > Reviews"],
    ),
    destroy=extend_schema(
        operation_id="delete_product_review",
        summary="Delete your review",
        description="Delete your own review (owner only)",
        tags=["Products > Reviews"],
    ),
)
class ReviewViewSet(viewsets.ViewSet):
    """ViewSet for product reviews."""
    pass
```

### 4. Search Views (Separate from Products)

```python
@extend_schema_view(
    search=extend_schema(
        operation_id="search_products",
        summary="Search products",
        description="""
        Full-text search across products.

        **Searches:** name, description, brand, tags
        **Receives:** q (query string), category (optional), limit
        """,
        parameters=[
            OpenApiParameter("q", type=str, required=True, description="Search query"),
            OpenApiParameter("category", type=str, description="Filter by category"),
            OpenApiParameter("limit", type=int, description="Max results"),
        ],
        tags=["Products > Search"],
    ),
    autocomplete=extend_schema(
        operation_id="autocomplete_products",
        summary="Autocomplete suggestions",
        description="Get product name suggestions for autocomplete",
        parameters=[
            OpenApiParameter("q", type=str, required=True, description="Search prefix (min 2 chars)"),
        ],
        tags=["Products > Search"],
    ),
    filters=extend_schema(
        operation_id="get_product_filters",
        summary="Get available filters",
        description="Get all available filter options (brands, categories, price ranges)",
        tags=["Products > Search"],
    ),
)
class SearchViewSet(viewsets.ViewSet):
    """ViewSet for product search operations."""
    pass
```

### 5. Internal APIs

```python
@extend_schema(
    operation_id="internal_get_product",
    summary="[INTERNAL] Get product information",
    description="""
    Internal API for service-to-service communication.

    **Security:** NOT exposed through Kong Gateway
    **Use Cases:** Payment service, Notification service
    """,
    tags=["Internal APIs"],
)
@api_view(["GET"])
def internal_get_product(request, product_id):
    pass
```

---

## 🎨 Tag Naming Conventions

### Hierarchical Tags (Nested in Swagger UI)

Use `>` to create hierarchy:

```python
tags=["Products"]                  # Top level
tags=["Products > Reviews"]        # Nested under Products
tags=["Products > Images"]         # Nested under Products
tags=["Products > Metrics"]        # Nested under Products
tags=["Products > Search"]         # Nested under Products
```

### Flat Tags (Separate Sections)

```python
tags=["Categories"]
tags=["Cart"]
tags=["Orders"]
tags=["Sellers"]
```

---

## 📊 Tag Organization Best Practices

### 1. **Group Related Endpoints**
```python
# All product CRUD operations
tags=["Products"]

# All cart operations
tags=["Cart"]
```

### 2. **Use Hierarchy for Nested Resources**
```python
# Reviews belong to products
tags=["Products > Reviews"]

# Images belong to products
tags=["Products > Images"]
```

### 3. **Mark Internal/Admin Endpoints**
```python
tags=["Internal APIs"]      # For service-to-service
tags=["Admin"]              # For admin-only
tags=["Monitoring"]         # For metrics/health
```

### 4. **Use Descriptive Names**
```python
✅ tags=["Products > Search"]
✅ tags=["Products > Reviews"]
✅ tags=["Internal APIs"]

❌ tags=["Misc"]
❌ tags=["Other"]
❌ tags=["API"]
```

---

## 🚀 Testing Your Tags

### 1. **Run Django Server**
```bash
python manage.py runserver
```

### 2. **Open Swagger UI**
```
http://localhost:8000/api/docs/
```

### 3. **Check Organization**
You should see endpoints grouped like:
```
📂 Categories
📂 Products
  📂 Search
  📂 Reviews
  📂 Images
  📂 Metrics
📂 Cart
📂 Orders
📂 Sellers
📂 User Profiles
📂 Internal APIs
📂 Monitoring
```

---

## 💡 Benefits of Good Tag Organization

✅ **Easy Navigation** - Find endpoints quickly
✅ **Logical Grouping** - Related endpoints together
✅ **Better UX** - Cleaner API documentation
✅ **Clear Hierarchy** - Understand relationships
✅ **Professional** - Well-organized appearance

---

## 🔄 Updating Existing Views

### Quick Checklist

- [ ] Import `extend_schema` and `extend_schema_view`
- [ ] Add `@extend_schema_view` to ViewSet classes
- [ ] Add `@extend_schema` to custom actions
- [ ] Add `@extend_schema` to function-based views
- [ ] Use consistent tag names
- [ ] Test in Swagger UI

---

## 📚 Additional Resources

- **drf-spectacular docs**: https://drf-spectacular.readthedocs.io/
- **OpenAPI tags**: https://swagger.io/docs/specification/grouping-operations-with-tags/
- **Authentication app example**: `authentication/api/views/auth_views.py`

---

**Open Swagger UI to see your organized API:** http://localhost:8000/api/docs/ 🚀
