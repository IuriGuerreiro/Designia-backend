# Marketplace API Documentation Guide

## 🚀 Quick Start

### Accessing API Documentation

The Designia Marketplace API has **interactive documentation** powered by Swagger UI and ReDoc.

#### Swagger UI (Interactive API Explorer)
```
http://localhost:8000/api/docs/
```
- **Test endpoints directly** in the browser
- **Authorization support** - Add your JWT token once, use for all requests
- **Request/Response examples** for every endpoint
- **Try it out** feature for live API testing

#### ReDoc (Clean Documentation)
```
http://localhost:8000/api/redoc/
```
- Beautiful, responsive API documentation
- Search functionality
- Code samples in multiple languages
- Better for reading/reference

#### OpenAPI Schema (JSON)
```
http://localhost:8000/api/schema/
```
- Download the raw OpenAPI 3.0 schema
- Import into Postman, Insomnia, or other API clients
- Generate client SDKs

#### Static YAML File
```
Designia-backend/docs/api/marketplace-openapi.yaml
```
- Standalone OpenAPI specification
- Version controlled
- Can be imported into any OpenAPI-compatible tool

---

## 🔐 Authentication

Most marketplace endpoints require JWT authentication.

### Getting a JWT Token

1. **Login** to get access token:
   ```bash
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{
       "email": "user@example.com",
       "password": "yourpassword"
     }'
   ```

2. **Response** contains your tokens:
   ```json
   {
     "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   }
   ```

3. **Use the access token** in all authenticated requests:
   ```bash
   curl -X GET http://localhost:8000/api/marketplace/cart/ \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```

### Using Authentication in Swagger UI

1. Open http://localhost:8000/api/docs/
2. Click the **"Authorize"** button (green lock icon, top right)
3. Enter your token in the format: `Bearer <your-access-token>`
4. Click **"Authorize"** then **"Close"**
5. All subsequent requests will include your token automatically

---

## 📚 API Endpoint Categories

### 🛍️ Products (`/api/marketplace/products/`)
Browse, search, and manage product catalog.

**Public Endpoints** (No auth required):
- `GET /products/` - List products with filtering/pagination
- `GET /products/{slug}/` - Get product details
- `GET /products/search/?q=keyword` - Search products
- `GET /products/autocomplete/?q=prefix` - Autocomplete suggestions
- `GET /products/filters/` - Get available filters

**Protected Endpoints** (Seller only):
- `POST /products/` - Create new product
- `PUT /products/{slug}/` - Update product
- `DELETE /products/{slug}/` - Delete product

### 🗂️ Categories (`/api/marketplace/categories/`)
Product category management.

**Public Endpoints**:
- `GET /categories/` - List all categories
- `GET /categories/{id}/` - Get category details

### 🛒 Cart (`/api/marketplace/cart/`)
Shopping cart operations (requires authentication).

**Protected Endpoints**:
- `GET /cart/` - Get current cart
- `POST /cart/add/` - Add item to cart
- `PUT /cart/update/` - Update item quantity
- `DELETE /cart/remove/` - Remove item
- `DELETE /cart/` - Clear entire cart
- `GET /cart/validate/` - Validate cart before checkout

### 📦 Orders (`/api/marketplace/orders/`)
Order lifecycle management (requires authentication).

**Protected Endpoints**:
- `GET /orders/` - List user's orders
- `POST /orders/` - Create order from cart
- `GET /orders/{id}/` - Get order details
- `POST /orders/{id}/cancel/` - Cancel order

### ⭐ Reviews (`/api/marketplace/reviews/`)
Product reviews and ratings.

**Public Endpoints**:
- `GET /reviews/?product={product_id}` - List reviews

**Protected Endpoints**:
- `POST /reviews/` - Create review
- `PUT /reviews/{id}/` - Update own review
- `DELETE /reviews/{id}/` - Delete own review

### 👤 Seller (`/api/marketplace/sellers/`)
Seller profile information.

**Public Endpoints**:
- `GET /sellers/{seller_id}/` - Get seller profile

### 📊 Metrics (`/api/marketplace/metrics/`)
Prometheus metrics endpoint.

**Public Endpoint**:
- `GET /metrics/` - Prometheus metrics (for monitoring)

### 🔒 Internal APIs (`/api/marketplace/internal/`)
**⚠️ NOT PUBLICLY EXPOSED** - Internal service-to-service only.

- `GET /internal/products/{product_id}/` - Get product info (for Payment service)
- `GET /internal/orders/{order_id}/` - Get order info (for Payment webhooks)

---

## 🎯 Common Use Cases

### 1. Browse Products
```bash
# List all products (paginated)
GET /api/marketplace/products/

# Filter by category
GET /api/marketplace/products/?category=electronics

# Filter by price range
GET /api/marketplace/products/?price_min=100&price_max=500

# Show only in-stock items
GET /api/marketplace/products/?in_stock=true

# Sort by price (ascending)
GET /api/marketplace/products/?ordering=price
```

### 2. Search Products
```bash
# Search by keyword
GET /api/marketplace/products/search/?q=iPhone

# Search with category filter
GET /api/marketplace/products/search/?q=phone&category=electronics

# Autocomplete for search box
GET /api/marketplace/products/autocomplete/?q=iPh
```

### 3. Add to Cart and Checkout
```bash
# 1. Add items to cart
POST /api/marketplace/cart/add/
{
  "product_id": "123e4567-e89b-12d3-a456-426614174000",
  "quantity": 2
}

# 2. View cart
GET /api/marketplace/cart/

# 3. Validate cart before checkout
GET /api/marketplace/cart/validate/

# 4. Create order
POST /api/marketplace/orders/
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

### 4. Manage Orders
```bash
# List all orders
GET /api/marketplace/orders/

# Filter by status
GET /api/marketplace/orders/?status=pending_payment

# Get order details
GET /api/marketplace/orders/{order_id}/

# Cancel order (before shipment)
POST /api/marketplace/orders/{order_id}/cancel/
{
  "reason": "Changed my mind"
}
```

### 5. Seller Operations
```bash
# Create product (seller only)
POST /api/marketplace/products/
{
  "name": "iPhone 15 Pro Max",
  "description": "Latest iPhone with A17 chip",
  "price": "1199.00",
  "category_id": 1,
  "stock_quantity": 10,
  "condition": "new",
  "brand": "Apple"
}

# Update product
PATCH /api/marketplace/products/iphone-15-pro-max/
{
  "price": "1099.00",
  "stock_quantity": 5
}

# View seller profile (public)
GET /api/marketplace/sellers/{seller_id}/
```

---

## 🔍 Filtering and Pagination

### Filtering Options

Products can be filtered by multiple parameters:

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `category` | string | Category slug | `category=electronics` |
| `seller` | integer | Seller user ID | `seller=42` |
| `price_min` | decimal | Minimum price | `price_min=100` |
| `price_max` | decimal | Maximum price | `price_max=500` |
| `condition` | enum | Product condition | `condition=new` |
| `brand` | string | Brand name | `brand=Apple` |
| `in_stock` | boolean | Only in-stock | `in_stock=true` |
| `is_featured` | boolean | Only featured | `is_featured=true` |

### Sorting Options

Use the `ordering` parameter:

| Value | Description |
|-------|-------------|
| `-created_at` | Newest first (default) |
| `created_at` | Oldest first |
| `price` | Price low to high |
| `-price` | Price high to low |
| `-view_count` | Most viewed first |
| `-favorite_count` | Most favorited first |

### Pagination

All list endpoints support pagination:

```bash
GET /api/marketplace/products/?page=2&page_size=20
```

**Response includes pagination metadata:**
```json
{
  "count": 150,
  "page": 2,
  "page_size": 20,
  "num_pages": 8,
  "has_next": true,
  "has_previous": true,
  "results": [...]
}
```

---

## ⚡ Rate Limiting

Requests are rate-limited via **Kong API Gateway**:

| Endpoint Type | Limit | Purpose |
|---------------|-------|---------|
| Public endpoints (products, search) | 100 req/min | General browsing |
| Cart operations | 60 req/min | Prevent bot abuse |
| Authenticated endpoints | 60 req/min | User actions |
| Internal APIs | 1000 req/min | Service-to-service |

**Rate limit exceeded response:**
```json
{
  "detail": "Too many requests. Please try again later."
}
```
HTTP Status: `429 Too Many Requests`

---

## 🐛 Error Handling

### Standard Error Response Format

```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "detail": "Additional context"
}
```

### Common HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| `200` | Success | Request completed successfully |
| `201` | Created | Resource created (e.g., order) |
| `204` | No Content | Successful delete operation |
| `400` | Bad Request | Validation error, invalid input |
| `401` | Unauthorized | Missing or invalid JWT token |
| `403` | Forbidden | Not the owner, insufficient permissions |
| `404` | Not Found | Resource doesn't exist |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Server-side error |

### Example Error Responses

**Validation Error:**
```json
{
  "name": ["This field is required."],
  "price": ["Ensure this value is greater than or equal to 0."]
}
```

**Business Logic Error:**
```json
{
  "error": "reservation_failed",
  "message": "Failed to reserve stock for iPhone 15: Insufficient stock"
}
```

**Authentication Error:**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

---

## 🧪 Testing with cURL

### Complete Example: Creating an Order

```bash
# 1. Login
ACCESS_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}' \
  | jq -r '.access')

# 2. Browse products
curl -X GET "http://localhost:8000/api/marketplace/products/?category=electronics&in_stock=true" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 3. Add to cart
curl -X POST http://localhost:8000/api/marketplace/cart/add/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "123e4567-e89b-12d3-a456-426614174000",
    "quantity": 1
  }'

# 4. Validate cart
curl -X GET http://localhost:8000/api/marketplace/cart/validate/ \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 5. Create order
curl -X POST http://localhost:8000/api/marketplace/orders/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "shipping_address": {
      "street": "123 Main St",
      "city": "New York",
      "state": "NY",
      "postal_code": "10001",
      "country": "USA"
    },
    "buyer_notes": "Please call before delivery"
  }'

# 6. View order status
ORDER_ID="<order-id-from-step-5>"
curl -X GET "http://localhost:8000/api/marketplace/orders/$ORDER_ID/" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## 🛠️ Importing into API Clients

### Postman

1. Open Postman
2. Click **Import** button
3. Choose **Link** tab
4. Enter: `http://localhost:8000/api/schema/`
5. Click **Continue** → **Import**
6. Set up environment variable for JWT token

### Insomnia

1. Open Insomnia
2. Click **Create** → **Import**
3. Choose **From URL**
4. Enter: `http://localhost:8000/api/schema/`
5. Click **Fetch and Import**

### VS Code REST Client

Create a `.http` file:

```http
@baseUrl = http://localhost:8000/api/marketplace
@token = your-jwt-token-here

### Login
POST http://localhost:8000/api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}

### List Products
GET {{baseUrl}}/products/
Authorization: Bearer {{token}}

### Add to Cart
POST {{baseUrl}}/cart/add/
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "product_id": "123e4567-e89b-12d3-a456-426614174000",
  "quantity": 2
}
```

---

## 📊 Monitoring & Observability

### Prometheus Metrics

Access marketplace metrics:
```
http://localhost:8000/api/marketplace/metrics/
```

**Available Metrics:**
- `marketplace_orders_placed_total{status="success|failure"}` - Total orders
- `marketplace_order_value` - Order value histogram
- `marketplace_stock_reservation_failure` - Stock failures
- `marketplace_internal_api_calls_total{endpoint,status}` - Internal API calls

### Jaeger Tracing

View distributed traces:
```
http://localhost:16686
```

Search for traces by:
- Service: `marketplace-service`
- Operation: `order_create_transaction`, `catalog_list_products`

### Prometheus Dashboard

Query metrics:
```
http://localhost:9090
```

**Example queries:**
```promql
# Order rate (orders per second)
rate(marketplace_orders_placed_total[5m])

# Failed orders percentage
rate(marketplace_orders_placed_total{status="failure"}[5m])
/
rate(marketplace_orders_placed_total[5m]) * 100

# Average order value
avg(marketplace_order_value)
```

---

## 🔗 Related Documentation

- **Authentication API**: `/docs/api/auth-openapi.yaml`
- **Kong Gateway Setup**: `/infrastructure/kong/README.md`
- **Phase 3 Tech Spec**: `/docs/sprint-artifacts/tech-spec-marketplace-refactoring-phase3.md`
- **Backend Architecture**: `/DOCS/ARCHITECTURE.md`

---

## 💡 Tips & Best Practices

### 1. **Use Pagination**
Always paginate large result sets to avoid performance issues:
```bash
GET /api/marketplace/products/?page=1&page_size=20
```

### 2. **Validate Cart Before Checkout**
Always validate the cart before creating an order:
```bash
GET /api/marketplace/cart/validate/
```

### 3. **Handle Rate Limits Gracefully**
Implement exponential backoff when receiving `429` responses.

### 4. **Use Filters Efficiently**
Combine multiple filters to narrow results:
```bash
GET /products/?category=electronics&price_max=500&in_stock=true
```

### 5. **Cache Product Listings**
Product list responses can be cached for 5-10 minutes on the client side.

### 6. **Monitor Your Usage**
Check the `X-RateLimit-Remaining` header to track rate limit usage.

---

## 🆘 Support

### Issues & Questions
- **GitHub Issues**: https://github.com/your-org/designia/issues
- **Email**: api-support@designia.com
- **Slack**: #api-support

### Changelog
- **v1.0.0** (2025-12-11): Initial Marketplace API release with Phase 3 integration

---

**Happy coding! 🚀**
