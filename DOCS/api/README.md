# Marketplace API Documentation

**Complete API documentation for the Designia Marketplace platform**

---

## 📚 Documentation Files

This directory contains comprehensive documentation for all Marketplace API endpoints.

| File | Purpose | Best For |
|------|---------|----------|
| **[marketplace-openapi.yaml](./marketplace-openapi.yaml)** | Full OpenAPI 3.0 specification | Import into Postman/Insomnia |
| **[MARKETPLACE_ENDPOINTS_DETAIL.md](./MARKETPLACE_ENDPOINTS_DETAIL.md)** | Complete endpoint reference with "Receives/Returns" | Quick lookup, understanding data structures |
| **[API_DOCUMENTATION_GUIDE.md](./API_DOCUMENTATION_GUIDE.md)** | Comprehensive developer guide | Learning how to use the API |
| **[MARKETPLACE_API_QUICK_REFERENCE.md](./MARKETPLACE_API_QUICK_REFERENCE.md)** | Quick reference card | Cheat sheet for developers |

---

## 🚀 Quick Start

### 1. **Interactive Documentation (Swagger UI)**
```
http://localhost:8000/api/docs/
```

**Features:**
- ✅ Test endpoints directly in browser
- ✅ See request/response examples
- ✅ "What it receives" and "What it returns" for each endpoint
- ✅ One-click authentication
- ✅ Try it out feature

**How to use:**
1. Open http://localhost:8000/api/docs/
2. Click "Authorize" (green lock icon)
3. Get JWT token from `/api/auth/login`
4. Paste token and click "Authorize"
5. Click any endpoint → "Try it out" → Fill parameters → "Execute"

### 2. **Clean Documentation (ReDoc)**
```
http://localhost:8000/api/redoc/
```

**Features:**
- 📖 Beautiful, readable documentation
- 🔍 Search functionality
- 📱 Mobile-responsive
- 🎨 Professional presentation

### 3. **Download OpenAPI Schema**
```
http://localhost:8000/api/schema/
```

Download and import into your favorite API client.

---

## 📋 Endpoint Categories

### 🛍️ **Products** (`/api/marketplace/products/`)
- List products with filtering/pagination
- Get product details
- Create/Update/Delete products (Seller only)
- Search products
- Autocomplete suggestions
- Get filter options

**See:** [MARKETPLACE_ENDPOINTS_DETAIL.md#products](./MARKETPLACE_ENDPOINTS_DETAIL.md#-products)

### 🗂️ **Categories** (`/api/marketplace/categories/`)
- List all categories
- Get category details

### 🛒 **Cart** (`/api/marketplace/cart/`)
- Get cart
- Add/Update/Remove items
- Clear cart
- Validate cart before checkout

**See:** [MARKETPLACE_ENDPOINTS_DETAIL.md#cart](./MARKETPLACE_ENDPOINTS_DETAIL.md#-cart)

### 📦 **Orders** (`/api/marketplace/orders/`)
- List user's orders
- Create order from cart
- Get order details
- Cancel order

**See:** [MARKETPLACE_ENDPOINTS_DETAIL.md#orders](./MARKETPLACE_ENDPOINTS_DETAIL.md#-orders)

### ⭐ **Reviews** (`/api/marketplace/reviews/`)
- List reviews
- Create/Update/Delete reviews

### 👤 **Seller** (`/api/marketplace/sellers/`)
- Get seller profile

### 📊 **Metrics & Internal** (`/api/marketplace/metrics/`)
- Prometheus metrics
- Internal product API (service-to-service)
- Internal order API (service-to-service)

---

## 🎯 Example: Complete Purchase Flow

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r '.access')

# 2. Browse products
curl "http://localhost:8000/api/marketplace/products/?category=electronics&in_stock=true"

# 3. Add to cart
curl -X POST http://localhost:8000/api/marketplace/cart/add/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id":"uuid-here","quantity":1}'

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

---

## 📊 What's Documented

### ✅ Swagger UI Shows:

For **every endpoint**, you'll see:

1. **Summary** - What the endpoint does
2. **Description** - Detailed explanation with:
   - **What it receives** (path params, query params, request body)
   - **What it returns** (response structure)
   - **Flow** (multi-step processes)
   - **Rate Limiting** info
   - **Security** requirements
3. **Request Schema** - Exactly what to send
4. **Response Examples** - Real JSON examples
5. **Status Codes** - All possible responses
6. **Try it out** - Interactive testing

### Example: Cart Add Item

When you open `/cart/add/` in Swagger UI, you'll see:

**What it receives:**
```json
{
  "product_id": "123e4567-e89b-12d3-a456-426614174000",
  "quantity": 2
}
```

**What it returns (200):**
```json
{
  "items": [
    {
      "product": {...},
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

**What it returns (400 - Out of Stock):**
```json
{
  "error": "out_of_stock",
  "message": "Product is out of stock"
}
```

---

## 🔐 Authentication

Most endpoints require JWT authentication.

### Getting a Token:
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "yourpassword"
  }'
```

### Using the Token:
```bash
curl -H "Authorization: Bearer <your-access-token>" \
  http://localhost:8000/api/marketplace/cart/
```

### In Swagger UI:
1. Click **"Authorize"** button (green lock icon)
2. Enter: `Bearer <your-access-token>`
3. Click **"Authorize"** → **"Close"**
4. All requests now include your token automatically

---

## 📖 Documentation Style

Following the same pattern as `authentication/` app:

```python
@extend_schema(
    operation_id="internal_get_product",
    summary="[INTERNAL] Get product information",
    description="""
    **What it receives:**
    - product_id (UUID in URL): The product to fetch

    **What it returns:**
    - Product ID, name, price, stock quantity, active status, seller ID

    **Security:**
    - Should only be accessible within internal network

    **Use Cases:**
    - Payment service checking product price
    - Notification service getting product details
    """,
    responses={
        200: OpenApiResponse(
            response=InternalProductInfoSerializer,
            description="Product information retrieved successfully",
            examples=[...]
        ),
        404: OpenApiResponse(...)
    },
    tags=["Internal APIs"]
)
@api_view(["GET"])
def internal_get_product(request, product_id):
    """
    **Receives:** product_id (UUID)
    **Returns:** JSON with price, stock, active status
    """
    ...
```

---

## 🛠️ Tools Integration

### Postman
1. Import from URL: `http://localhost:8000/api/schema/`
2. Set up environment with JWT token
3. Start testing

### Insomnia
1. Import → From URL → `http://localhost:8000/api/schema/`
2. Configure Bearer token
3. Test endpoints

### VS Code REST Client
```http
@baseUrl = http://localhost:8000/api/marketplace
@token = your-jwt-token

### List Products
GET {{baseUrl}}/products/

### Add to Cart
POST {{baseUrl}}/cart/add/
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "product_id": "uuid",
  "quantity": 1
}
```

---

## 📊 Monitoring

### Prometheus Metrics
```
http://localhost:9090
```

**Key Metrics:**
- `marketplace_orders_placed_total` - Order count
- `marketplace_order_value` - Order values
- `marketplace_stock_reservation_failure` - Stock issues
- `marketplace_internal_api_calls_total` - Internal API usage

### Jaeger Tracing
```
http://localhost:16686
```

**Key Traces:**
- `order_create_transaction` - Order creation flow
- `catalog_list_products` - Product listing

---

## 🐛 Common Issues

### "Authentication credentials were not provided"
**Solution:** Add `Authorization: Bearer <token>` header

### "User is not a seller"
**Solution:** Apply for seller status via `/api/auth/seller/apply`

### "Product out of stock"
**Solution:** Product no longer available, check stock_quantity

### "Cannot cancel order in status 'shipped'"
**Solution:** Orders can only be cancelled before shipment

### "Too many requests"
**Solution:** You've hit the rate limit, wait 60 seconds

---

## 📚 Learn More

- **Phase 3 Tech Spec**: [/docs/sprint-artifacts/tech-spec-marketplace-refactoring-phase3.md](../../sprint-artifacts/tech-spec-marketplace-refactoring-phase3.md)
- **Kong Gateway Setup**: [/infrastructure/kong/README.md](../../../infrastructure/kong/README.md)
- **Backend Architecture**: [/DOCS/ARCHITECTURE.md](../../ARCHITECTURE.md)

---

## 🎯 What Makes This Different

Unlike typical API docs, ours include:

✅ **"What it receives" / "What it returns"** for every endpoint
✅ **Real JSON examples** with actual data
✅ **Interactive testing** via Swagger UI
✅ **Error responses** with solutions
✅ **Flow diagrams** for complex operations
✅ **Rate limiting** information
✅ **Security notes** for internal APIs
✅ **Use cases** for each endpoint
✅ **Side effects** clearly marked
✅ **Authentication** requirements per endpoint

---

## 🚀 Start Exploring!

**Open Swagger UI now:** http://localhost:8000/api/docs/

You'll see all marketplace endpoints with complete documentation showing exactly what each endpoint receives and returns, just like the authentication app! 🎉
