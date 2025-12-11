# Marketplace API - Quick Reference Card

## 🔗 Documentation URLs

| Resource | URL | Description |
|----------|-----|-------------|
| **Swagger UI** | http://localhost:8000/api/docs/ | Interactive API testing |
| **ReDoc** | http://localhost:8000/api/redoc/ | Clean documentation |
| **OpenAPI Schema** | http://localhost:8000/api/schema/ | JSON schema |
| **Static YAML** | `docs/api/marketplace-openapi.yaml` | Version-controlled spec |

## 🔐 Authentication

```bash
# Get JWT token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'

# Use token in requests
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/marketplace/cart/
```

## 📋 Endpoint Quick Reference

### Products

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/products/` | ❌ | List products (paginated) |
| `GET` | `/products/{slug}/` | ❌ | Get product details |
| `POST` | `/products/` | ✅ | Create product (seller only) |
| `PUT` | `/products/{slug}/` | ✅ | Update product (owner only) |
| `PATCH` | `/products/{slug}/` | ✅ | Partial update |
| `DELETE` | `/products/{slug}/` | ✅ | Delete product |

### Search

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/products/search/?q={query}` | ❌ | Search products |
| `GET` | `/products/autocomplete/?q={prefix}` | ❌ | Autocomplete suggestions |
| `GET` | `/products/filters/` | ❌ | Get filter options |

### Categories

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/categories/` | ❌ | List categories |
| `GET` | `/categories/{id}/` | ❌ | Get category details |

### Cart

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/cart/` | ✅ | Get current cart |
| `POST` | `/cart/add/` | ✅ | Add item to cart |
| `PUT` | `/cart/update/` | ✅ | Update item quantity |
| `DELETE` | `/cart/remove/` | ✅ | Remove item |
| `DELETE` | `/cart/` | ✅ | Clear cart |
| `GET` | `/cart/validate/` | ✅ | Validate cart |

### Orders

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/orders/` | ✅ | List user's orders |
| `POST` | `/orders/` | ✅ | Create order from cart |
| `GET` | `/orders/{id}/` | ✅ | Get order details |
| `POST` | `/orders/{id}/cancel/` | ✅ | Cancel order |

### Reviews

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/reviews/?product={id}` | ❌ | List reviews |
| `POST` | `/reviews/` | ✅ | Create review |
| `PUT` | `/reviews/{id}/` | ✅ | Update review |
| `DELETE` | `/reviews/{id}/` | ✅ | Delete review |

### Seller

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/sellers/{id}/` | ❌ | Get seller profile |

### Metrics & Internal

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/metrics/` | ❌ | Prometheus metrics |
| `GET` | `/internal/products/{id}/` | 🔒 | Internal product API |
| `GET` | `/internal/orders/{id}/` | 🔒 | Internal order API |

**Legend**: ✅ = Auth Required | ❌ = Public | 🔒 = Internal Only

## 🎯 Common Query Parameters

### Products List (`/products/`)

```bash
# Pagination
?page=1&page_size=20

# Filtering
?category=electronics
?seller=42
?price_min=100&price_max=500
?condition=new
?brand=Apple
?in_stock=true
?is_featured=true

# Sorting
?ordering=-created_at  # Newest first (default)
?ordering=price        # Cheapest first
?ordering=-price       # Most expensive first
?ordering=-view_count  # Most viewed
```

## 📦 Request Body Examples

### Add to Cart
```json
POST /cart/add/
{
  "product_id": "123e4567-e89b-12d3-a456-426614174000",
  "quantity": 2
}
```

### Create Order
```json
POST /orders/
{
  "shipping_address": {
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "postal_code": "10001",
    "country": "USA"
  },
  "buyer_notes": "Please ring doorbell"
}
```

### Create Product (Seller)
```json
POST /products/
{
  "name": "iPhone 15 Pro",
  "description": "Latest iPhone",
  "price": "999.00",
  "category_id": 1,
  "stock_quantity": 10,
  "condition": "new",
  "brand": "Apple"
}
```

### Create Review
```json
POST /reviews/
{
  "product_id": "123e4567-e89b-12d3-a456-426614174000",
  "rating": 5,
  "title": "Excellent product!",
  "comment": "Works perfectly, fast shipping."
}
```

## 🚦 HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| `200` | OK | Successful request |
| `201` | Created | Resource created (order, review) |
| `204` | No Content | Successful delete |
| `400` | Bad Request | Validation error |
| `401` | Unauthorized | Missing/invalid token |
| `403` | Forbidden | Not owner/seller |
| `404` | Not Found | Resource doesn't exist |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Server Error | Internal error |

## ⚡ Rate Limits (Kong Gateway)

| Endpoint Type | Limit |
|---------------|-------|
| Public (products, search) | 100/min |
| Cart operations | 60/min |
| Authenticated endpoints | 60/min |
| Internal APIs | 1000/min |

## 🔍 Product Conditions

| Value | Description |
|-------|-------------|
| `new` | Brand new, unused |
| `like_new` | Barely used, excellent condition |
| `used` | Previously owned, good condition |
| `refurbished` | Professionally restored |

## 📊 Order Status Flow

```
pending_payment → payment_confirmed → awaiting_shipment → shipped → delivered

                  ↓
               cancelled (before shipment)
                  ↓
               refunded (after payment)
```

## 🛠️ Testing Commands

### Complete Purchase Flow
```bash
# Set token
TOKEN="your-jwt-token"

# 1. Browse products
curl "http://localhost:8000/api/marketplace/products/?category=electronics"

# 2. Add to cart
curl -X POST http://localhost:8000/api/marketplace/cart/add/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id":"uuid-here","quantity":1}'

# 3. View cart
curl http://localhost:8000/api/marketplace/cart/ \
  -H "Authorization: Bearer $TOKEN"

# 4. Validate cart
curl http://localhost:8000/api/marketplace/cart/validate/ \
  -H "Authorization: Bearer $TOKEN"

# 5. Create order
curl -X POST http://localhost:8000/api/marketplace/orders/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "shipping_address": {
      "street": "123 Main St",
      "city": "New York",
      "state": "NY",
      "postal_code": "10001",
      "country": "USA"
    }
  }'

# 6. Check order status
curl http://localhost:8000/api/marketplace/orders/{order-id}/ \
  -H "Authorization: Bearer $TOKEN"
```

## 📈 Monitoring

### Prometheus Metrics
```
http://localhost:9090
```

**Key Metrics:**
- `marketplace_orders_placed_total` - Order count
- `marketplace_order_value` - Order values
- `marketplace_stock_reservation_failure` - Stock issues

### Jaeger Tracing
```
http://localhost:16686
```

**Key Traces:**
- `order_create_transaction` - Order creation flow
- `catalog_list_products` - Product listing

### Kong Admin API
```
http://localhost:8001
```

## 🐛 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Authentication credentials were not provided` | No token | Add `Authorization: Bearer <token>` header |
| `You do not own this product` | Not the owner | Only owner can update/delete |
| `User is not a seller` | Not verified seller | Apply for seller status via `/api/auth/seller/apply` |
| `Failed to reserve stock` | Out of stock | Product no longer available |
| `Cannot cancel order in status 'shipped'` | Too late | Orders can only be cancelled before shipment |
| `Too many requests` | Rate limit hit | Wait 60 seconds, then retry |

## 📚 See Also

- **Full Guide**: `docs/api/API_DOCUMENTATION_GUIDE.md`
- **OpenAPI Spec**: `docs/api/marketplace-openapi.yaml`
- **Kong Setup**: `infrastructure/kong/README.md`
- **Phase 3 Spec**: `docs/sprint-artifacts/tech-spec-marketplace-refactoring-phase3.md`

---

**Quick Tip**: Open Swagger UI at http://localhost:8000/api/docs/ for interactive testing! 🚀
