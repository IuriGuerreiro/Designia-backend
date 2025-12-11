# Marketplace API Endpoints - Detailed Documentation

**Complete reference of what each endpoint receives and returns**

---

## 🛍️ PRODUCTS

### `GET /api/marketplace/products/`
**List all products (paginated)**

**Receives:**
```
Query Parameters:
- page (integer, default: 1): Page number
- page_size (integer, default: 20, max: 100): Items per page
- category (string): Filter by category slug (e.g., "electronics")
- seller (integer): Filter by seller user ID
- price_min (decimal): Minimum price filter
- price_max (decimal): Maximum price filter
- condition (enum): "new", "like_new", "used", "refurbished"
- brand (string): Filter by brand name
- in_stock (boolean): Show only in-stock items
- is_featured (boolean): Show only featured products
- ordering (string): Sort order
  Options: -created_at (newest first, default), created_at, price, -price, -view_count, -favorite_count
```

**Returns:**
```json
{
  "count": 150,
  "page": 1,
  "page_size": 20,
  "num_pages": 8,
  "has_next": true,
  "has_previous": false,
  "results": [
    {
      "id": "uuid",
      "name": "Product Name",
      "slug": "product-name",
      "short_description": "Brief description",
      "price": "99.99",
      "original_price": "129.99",
      "discount_percentage": 23.08,
      "stock_quantity": 10,
      "condition": "new",
      "is_featured": false,
      "primary_image": "https://cdn.example.com/image.jpg",
      "seller": {
        "id": 42,
        "username": "seller123",
        "seller_rating": 4.5
      },
      "category": {
        "id": 1,
        "name": "Electronics",
        "slug": "electronics"
      },
      "view_count": 342,
      "favorite_count": 15,
      "average_rating": 4.3,
      "review_count": 27,
      "created_at": "2025-12-01T10:00:00Z"
    }
  ]
}
```

**Auth:** ❌ Not required (Public)
**Rate Limit:** 100 requests/minute

---

### `GET /api/marketplace/products/{slug}/`
**Get product details**

**Receives:**
```
Path Parameters:
- slug (string): Product slug (URL-friendly identifier)
```

**Returns:**
```json
{
  "id": "uuid",
  "name": "iPhone 15 Pro Max",
  "slug": "iphone-15-pro-max",
  "description": "Full product description with features...",
  "short_description": "Latest iPhone model",
  "price": "1199.00",
  "original_price": "1299.00",
  "discount_percentage": 7.70,
  "stock_quantity": 5,
  "condition": "new",
  "brand": "Apple",
  "model": "A2894",
  "colors": ["Titanium Blue", "Titanium Black"],
  "materials": "Titanium, Glass",
  "dimensions": {
    "length": 159.9,
    "width": 76.7,
    "height": 8.25
  },
  "weight": 221,
  "tags": ["smartphone", "5g", "premium"],
  "is_digital": false,
  "is_featured": true,
  "primary_image": "https://cdn.example.com/iphone.jpg",
  "images": [
    {
      "id": 1,
      "image_url": "https://cdn.example.com/img1.jpg",
      "is_primary": true,
      "order": 0
    }
  ],
  "seller": {
    "id": 42,
    "username": "applestore",
    "seller_rating": 4.9
  },
  "category": {
    "id": 1,
    "name": "Electronics",
    "slug": "electronics"
  },
  "view_count": 15243,
  "favorite_count": 892,
  "average_rating": 4.7,
  "review_count": 453,
  "reviews": [
    {
      "id": 1,
      "reviewer": {"id": 10, "username": "john_doe"},
      "rating": 5,
      "title": "Amazing!",
      "comment": "Best phone ever",
      "verified_purchase": true,
      "created_at": "2025-12-10T14:30:00Z"
    }
  ],
  "created_at": "2025-12-01T10:00:00Z"
}
```

**Auth:** ❌ Not required (Public)
**Rate Limit:** 100 requests/minute
**Side Effect:** Increments view_count on each access

---

### `POST /api/marketplace/products/`
**Create a new product (Seller only)**

**Receives:**
```json
{
  "name": "Product Name",
  "description": "Full product description (optional)",
  "short_description": "Brief description (optional)",
  "price": "99.99",
  "original_price": "129.99" (optional),
  "category_id": 1,
  "stock_quantity": 10,
  "condition": "new",
  "brand": "Brand Name" (optional),
  "model": "Model123" (optional),
  "colors": ["Red", "Blue"] (optional),
  "materials": "Cotton, Polyester" (optional),
  "tags": ["tag1", "tag2"] (optional),
  "is_digital": false (default: false),
  "images": [file uploads] (optional, multipart/form-data)
}
```

**Returns:**
```json
{
  "id": "uuid",
  "name": "Product Name",
  "slug": "product-name",
  "price": "99.99",
  "stock_quantity": 10,
  "seller": {...},
  "created_at": "2025-12-11T18:30:00Z",
  ...
}
```

**Auth:** ✅ Required + Must be verified seller
**Rate Limit:** 60 requests/minute
**Errors:**
- `403`: User is not a seller
- `400`: Validation error (invalid category, missing required fields)

---

### `PUT/PATCH /api/marketplace/products/{slug}/`
**Update product (Owner only)**

**Receives:**
```json
{
  "name": "Updated Name" (optional),
  "description": "Updated description" (optional),
  "price": "89.99" (optional),
  "stock_quantity": 15 (optional),
  "is_active": true (optional),
  "is_featured": false (optional)
}
```

**Returns:** Updated product object (same as GET detail)

**Auth:** ✅ Required + Must be product owner
**Rate Limit:** 60 requests/minute
**Errors:**
- `403`: Not the product owner
- `404`: Product not found

---

### `DELETE /api/marketplace/products/{slug}/`
**Delete product (Soft delete)**

**Receives:** None (slug in URL)

**Returns:** `204 No Content`

**Auth:** ✅ Required + Must be product owner
**Rate Limit:** 60 requests/minute
**Note:** Performs soft delete (sets is_active=False), doesn't actually delete from database

---

## 🔍 SEARCH

### `GET /api/marketplace/products/search/`
**Search products**

**Receives:**
```
Query Parameters:
- q (string, required): Search query
- category (string, optional): Filter by category
- limit (integer, default: 20, max: 100): Max results
```

**Returns:** Array of product objects (same structure as product list)

**Auth:** ❌ Not required
**Rate Limit:** 100 requests/minute

---

### `GET /api/marketplace/products/autocomplete/`
**Get autocomplete suggestions**

**Receives:**
```
Query Parameters:
- q (string, required, min 2 chars): Search prefix
```

**Returns:**
```json
{
  "suggestions": ["iPhone 15", "iPhone 14", "iPhone 13 Pro"]
}
```

**Auth:** ❌ Not required
**Rate Limit:** 100 requests/minute

---

### `GET /api/marketplace/products/filters/`
**Get available filter options**

**Receives:** None

**Returns:**
```json
{
  "brands": ["Apple", "Samsung", "Sony"],
  "categories": [
    {"id": 1, "name": "Electronics", "slug": "electronics"},
    {"id": 2, "name": "Clothing", "slug": "clothing"}
  ],
  "price_range": {
    "min": "9.99",
    "max": "2999.99"
  }
}
```

**Auth:** ❌ Not required
**Rate Limit:** 100 requests/minute

---

## 🗂️ CATEGORIES

### `GET /api/marketplace/categories/`
**List all categories**

**Receives:** None

**Returns:**
```json
[
  {
    "id": 1,
    "name": "Electronics",
    "slug": "electronics",
    "description": "Electronic devices and accessories",
    "icon": "📱",
    "is_active": true,
    "product_count": 342
  }
]
```

**Auth:** ❌ Not required
**Rate Limit:** 100 requests/minute

---

### `GET /api/marketplace/categories/{id}/`
**Get category details**

**Receives:** Category ID in URL

**Returns:** Single category object (same structure as list)

**Auth:** ❌ Not required
**Rate Limit:** 100 requests/minute

---

## 🛒 CART

### `GET /api/marketplace/cart/`
**Get user's shopping cart**

**Receives:** None (user identified by JWT token)

**Returns:**
```json
{
  "items": [
    {
      "product": {
        "id": "uuid",
        "name": "Product Name",
        "price": "99.99",
        "stock_quantity": 10,
        "primary_image": "https://...",
        ...
      },
      "quantity": 2,
      "subtotal": "199.98"
    }
  ],
  "totals": {
    "subtotal": "199.98",
    "shipping": "15.00",
    "tax": "17.25",
    "total": "232.23"
  },
  "item_count": 2
}
```

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute

---

### `POST /api/marketplace/cart/add/`
**Add item to cart**

**Receives:**
```json
{
  "product_id": "123e4567-e89b-12d3-a456-426614174000",
  "quantity": 2
}
```

**Returns:** Updated cart object (same as GET cart)

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute (Bot prevention)
**Errors:**
- `400`: Product out of stock
- `400`: Product inactive
- `400`: Invalid quantity
- `404`: Product not found

---

### `PUT /api/marketplace/cart/update/`
**Update cart item quantity**

**Receives:**
```json
{
  "product_id": "uuid",
  "quantity": 3
}
```

**Returns:** Updated cart object

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute
**Note:** Set quantity to 0 to remove item

---

### `DELETE /api/marketplace/cart/remove/`
**Remove item from cart**

**Receives:**
```json
{
  "product_id": "uuid"
}
```

**Returns:** Updated cart object

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute

---

### `DELETE /api/marketplace/cart/`
**Clear entire cart**

**Receives:** None

**Returns:** `204 No Content`

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute

---

### `GET /api/marketplace/cart/validate/`
**Validate cart before checkout**

**Receives:** None

**Returns:**
```json
{
  "valid": false,
  "issues": [
    {
      "product_id": "uuid",
      "issue_type": "out_of_stock",
      "message": "iPhone 15 is out of stock"
    },
    {
      "product_id": "uuid2",
      "issue_type": "price_changed",
      "message": "Price changed from $99.99 to $89.99"
    }
  ]
}
```

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute
**Use Case:** Call this before order creation to check for issues

---

## 📦 ORDERS

### `GET /api/marketplace/orders/`
**List user's orders**

**Receives:**
```
Query Parameters:
- status (enum, optional): Filter by status
  Options: pending_payment, payment_confirmed, awaiting_shipment, shipped, delivered, cancelled, refunded
- page (integer, default: 1)
- page_size (integer, default: 20)
```

**Returns:**
```json
{
  "count": 42,
  "page": 1,
  "page_size": 20,
  "num_pages": 3,
  "results": [
    {
      "id": "uuid",
      "status": "shipped",
      "payment_status": "paid",
      "total_amount": "232.23",
      "created_at": "2025-12-10T10:00:00Z",
      "item_count": 2
    }
  ]
}
```

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute

---

### `POST /api/marketplace/orders/`
**Create order from cart**

**Receives:**
```json
{
  "shipping_address": {
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "postal_code": "10001",
    "country": "USA"
  },
  "buyer_notes": "Please ring doorbell (optional)"
}
```

**Returns:**
```json
{
  "id": "uuid",
  "status": "pending_payment",
  "payment_status": "pending",
  "buyer": {
    "id": 123,
    "username": "john_doe",
    "email": "john@example.com"
  },
  "items": [
    {
      "id": 1,
      "product": {...},
      "quantity": 2,
      "unit_price": "99.99",
      "total_price": "199.98",
      "product_name": "iPhone 15",
      "product_image": "https://..."
    }
  ],
  "subtotal": "199.98",
  "shipping_cost": "15.00",
  "tax_amount": "17.25",
  "discount_amount": "0.00",
  "total_amount": "232.23",
  "shipping_address": {...},
  "buyer_notes": "Please ring doorbell",
  "tracking_number": null,
  "shipping_carrier": null,
  "shipped_at": null,
  "delivered_at": null,
  "created_at": "2025-12-11T18:30:00Z"
}
```

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute
**Process:**
1. Validates cart (stock, active products)
2. Reserves inventory
3. Calculates totals (subtotal, shipping, tax)
4. Creates order with status "pending_payment"
5. Clears cart
6. Publishes OrderPlacedEvent

**Errors:**
- `400`: Cart is empty
- `400`: Cart validation failed (out of stock, inactive products)
- `400`: Failed to reserve stock

---

### `GET /api/marketplace/orders/{id}/`
**Get order details**

**Receives:** Order ID (UUID) in URL

**Returns:** Detailed order object (same as POST order response)

**Auth:** ✅ Required + Must be order owner
**Rate Limit:** 60 requests/minute
**Errors:**
- `403`: Not the order owner
- `404`: Order not found

---

### `POST /api/marketplace/orders/{id}/cancel/`
**Cancel order**

**Receives:**
```json
{
  "reason": "Changed my mind (optional)"
}
```

**Returns:** Updated order object with status "cancelled"

**Auth:** ✅ Required + Must be order owner
**Rate Limit:** 60 requests/minute
**Constraints:** Can only cancel if status is: pending_payment, payment_confirmed, or awaiting_shipment
**Process:** Releases reserved inventory back to stock
**Errors:**
- `400`: Cannot cancel order in status 'shipped' or 'delivered'
- `403`: Not the order owner

---

## ⭐ REVIEWS

### `GET /api/marketplace/reviews/`
**List reviews**

**Receives:**
```
Query Parameters:
- product (UUID, optional): Filter by product ID
```

**Returns:**
```json
[
  {
    "id": 1,
    "product": {
      "id": "uuid",
      "name": "iPhone 15"
    },
    "reviewer": {
      "id": 10,
      "username": "john_doe"
    },
    "rating": 5,
    "title": "Amazing product!",
    "comment": "Works perfectly, fast shipping",
    "verified_purchase": true,
    "created_at": "2025-12-10T14:30:00Z",
    "updated_at": "2025-12-10T14:30:00Z"
  }
]
```

**Auth:** ❌ Not required
**Rate Limit:** 60 requests/minute

---

### `POST /api/marketplace/reviews/`
**Create a review**

**Receives:**
```json
{
  "product_id": "uuid",
  "rating": 5,
  "title": "Great product!" (optional),
  "comment": "Detailed review text (optional)"
}
```

**Returns:** Created review object (same structure as GET)

**Auth:** ✅ Required
**Rate Limit:** 60 requests/minute
**Requirements:**
- Must have purchased the product
- One review per product per user

**Errors:**
- `400`: Already reviewed this product
- `400`: Haven't purchased this product
- `400`: Invalid rating (must be 1-5)

---

### `PUT /api/marketplace/reviews/{id}/`
**Update own review**

**Receives:** Updated review data (same as POST)

**Returns:** Updated review object

**Auth:** ✅ Required + Must be review owner
**Rate Limit:** 60 requests/minute

---

### `DELETE /api/marketplace/reviews/{id}/`
**Delete own review**

**Receives:** None (ID in URL)

**Returns:** `204 No Content`

**Auth:** ✅ Required + Must be review owner
**Rate Limit:** 60 requests/minute

---

## 👤 SELLER

### `GET /api/marketplace/sellers/{seller_id}/`
**Get seller profile (Public)**

**Receives:** Seller user ID in URL

**Returns:**
```json
{
  "id": 42,
  "username": "seller123",
  "seller_rating": 4.8,
  "total_sales": 342,
  "products_count": 45,
  "joined_date": "2024-01-15",
  "bio": "Professional seller specializing in electronics"
}
```

**Auth:** ❌ Not required
**Rate Limit:** 100 requests/minute

---

## 📊 METRICS & INTERNAL

### `GET /api/marketplace/metrics/`
**Prometheus metrics endpoint**

**Receives:** None

**Returns:** Plain text Prometheus metrics format
```
# HELP marketplace_orders_placed_total Total orders placed
# TYPE marketplace_orders_placed_total counter
marketplace_orders_placed_total{status="success"} 42
marketplace_orders_placed_total{status="failure"} 3
...
```

**Auth:** ❌ Not required
**Rate Limit:** 1000 requests/minute
**Use Case:** Scraped by Prometheus for monitoring

---

### `GET /api/marketplace/internal/products/{product_id}/`
**[INTERNAL] Get product info for services**

**Receives:** Product UUID in URL

**Returns:**
```json
{
  "id": "uuid",
  "name": "Product Name",
  "price": "99.99",
  "stock_quantity": 10,
  "is_active": true,
  "seller_id": 42
}
```

**Auth:** ❌ Not required (internal network only)
**Rate Limit:** 1000 requests/minute
**Security:** NOT exposed through Kong Gateway, only accessible within internal Docker network
**Use Cases:**
- Payment service checking price
- Notification service getting product details
- Inventory service validation

---

### `GET /api/marketplace/internal/orders/{order_id}/`
**[INTERNAL] Get order info for services**

**Receives:** Order UUID in URL

**Returns:**
```json
{
  "id": "uuid",
  "status": "pending_payment",
  "total_amount": "232.23",
  "buyer_id": 123,
  "payment_status": "pending",
  "created_at": "2025-12-11T18:30:00Z"
}
```

**Auth:** ❌ Not required (internal network only)
**Rate Limit:** 1000 requests/minute
**Security:** NOT exposed through Kong Gateway
**Use Cases:**
- Payment webhook processing
- Order status updates
- Analytics tracking

---

## 📋 Order Status Flow

```
pending_payment
    ↓
payment_confirmed
    ↓
awaiting_shipment
    ↓
shipped
    ↓
delivered

Can cancel: pending_payment, payment_confirmed, awaiting_shipment
Cannot cancel: shipped, delivered, cancelled, refunded
```

---

## 🚦 HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| `200` | OK | Successful GET/PUT/PATCH request |
| `201` | Created | Successfully created resource (POST) |
| `204` | No Content | Successfully deleted or cleared |
| `400` | Bad Request | Validation error, invalid input |
| `401` | Unauthorized | Missing or invalid JWT token |
| `403` | Forbidden | Not owner, insufficient permissions |
| `404` | Not Found | Resource doesn't exist |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Server-side error |

---

## 🔒 Authentication Summary

| Endpoint Type | Auth Required | Role Required |
|---------------|---------------|---------------|
| Product List/Detail/Search | ❌ No | None |
| Product Create/Update/Delete | ✅ Yes | Seller |
| Categories | ❌ No | None |
| Cart Operations | ✅ Yes | Customer |
| Order Operations | ✅ Yes | Customer |
| Reviews List | ❌ No | None |
| Reviews Create/Update/Delete | ✅ Yes | Customer |
| Seller Profile | ❌ No | None |
| Internal APIs | ❌ No (Network-protected) | Internal Services |

---

**Need interactive testing?** Open Swagger UI: http://localhost:8000/api/docs/ 🚀
