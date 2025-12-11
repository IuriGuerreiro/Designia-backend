# Marketplace API - URL Structure

**RESTful, organized, and logical endpoint structure**

---

## 📐 URL Organization Principles

The Marketplace API follows these organizational principles:

1. **Resource-based**: URLs represent resources (products, orders, cart)
2. **Hierarchical**: Nested resources under parent resources
3. **RESTful**: Standard HTTP methods (GET, POST, PUT, DELETE)
4. **Logical grouping**: Related endpoints grouped together
5. **Swagger grouping**: Organized into clear sections in API docs

---

## 🗂️ Complete URL Structure

### **📦 CATEGORIES**
```
/api/marketplace/categories/
├── GET    /                              # List all categories
└── GET    /{id}/                        # Get category details
```

**Swagger Group:** `Categories`

---

### **🛍️ PRODUCTS**
```
/api/marketplace/products/
├── GET    /                              # List products (with filters)
├── POST   /                              # Create product (seller only)
├── GET    /{slug}/                       # Get product details
├── PUT    /{slug}/                       # Update product (owner only)
├── PATCH  /{slug}/                       # Partial update product
├── DELETE /{slug}/                       # Delete product
│
├─ SEARCH & FILTERS
│  ├── GET    /search/                    # Search products
│  ├── GET    /autocomplete/              # Autocomplete suggestions
│  └── GET    /filters/                   # Get available filters
│
├─ REVIEWS (nested under product)
│  ├── GET    /{slug}/reviews/            # List product reviews
│  ├── POST   /{slug}/reviews/            # Create review for product
│  ├── GET    /{slug}/reviews/{id}/       # Get specific review
│  ├── PUT    /{slug}/reviews/{id}/       # Update review
│  └── DELETE /{slug}/reviews/{id}/       # Delete review
│
├─ IMAGES (nested under product)
│  ├── GET    /{slug}/images/             # List product images
│  ├── POST   /{slug}/images/             # Upload image
│  ├── GET    /{slug}/images/{id}/        # Get specific image
│  ├── PUT    /{slug}/images/{id}/        # Update image
│  └── DELETE /{slug}/images/{id}/        # Delete image
│
└─ METRICS (analytics)
   ├── GET    /metrics/                   # List metrics for all products
   └── GET    /{slug}/metrics/            # Get metrics for specific product
```

**Swagger Groups:**
- `Products` - Main CRUD operations
- `Products > Search` - Search and filtering
- `Products > Reviews` - Product reviews
- `Products > Images` - Product images
- `Products > Metrics` - Analytics

---

### **🛒 CART**
```
/api/marketplace/cart/
├── GET    /                              # Get user's cart
├── POST   /add/                          # Add item to cart
├── PUT    /update/                       # Update item quantity
├── DELETE /remove/                       # Remove item from cart
├── DELETE /                              # Clear entire cart
└── GET    /validate/                     # Validate cart before checkout
```

**Swagger Group:** `Cart`

**Custom Actions:**
- `add` - Add item to cart
- `update` - Update cart item
- `remove` - Remove cart item
- `validate` - Validate cart

---

### **📦 ORDERS**
```
/api/marketplace/orders/
├── GET    /                              # List user's orders
├── POST   /                              # Create order from cart
├── GET    /{id}/                         # Get order details
├── PUT    /{id}/                         # Update order (admin)
└── POST   /{id}/cancel/                  # Cancel order
```

**Swagger Group:** `Orders`

**Custom Actions:**
- `cancel` - Cancel an order

---

### **👤 SELLERS**
```
/api/marketplace/sellers/
├── GET    /{id}/                         # Get seller profile
└── GET    /{id}/products/                # List seller's products
```

**Swagger Group:** `Sellers`

---

### **👥 USER PROFILES**
```
/api/marketplace/profiles/
├── GET    /                              # List profiles (admin)
├── GET    /{id}/                         # Get user profile
├── PUT    /{id}/                         # Update profile
└── DELETE /{id}/                         # Delete profile
```

**Swagger Group:** `User Profiles`

---

### **🔒 INTERNAL APIs** (Service-to-Service)
```
/api/marketplace/internal/
├── GET    /products/{id}/                # Get product info (internal)
└── GET    /orders/{id}/                  # Get order info (internal)
```

**Swagger Group:** `Internal APIs`

**Security:** NOT exposed through Kong Gateway, only accessible within internal Docker network

---

### **📊 MONITORING**
```
/api/marketplace/
└── GET    /metrics/                      # Prometheus metrics endpoint
```

**Swagger Group:** `Monitoring`

---

## 🎯 URL Pattern Examples

### Before (Old Structure)
```
❌ /api/marketplace/reviews/                         # Disconnected from products
❌ /api/marketplace/reviews/?product_id=uuid         # Query param instead of nested
❌ /api/marketplace/metrics/                         # Not clear it's for products
```

### After (New Structure)
```
✅ /api/marketplace/products/{slug}/reviews/         # Clearly nested under product
✅ /api/marketplace/products/{slug}/reviews/{id}/    # Hierarchical and RESTful
✅ /api/marketplace/products/metrics/                # Clear relationship to products
✅ /api/marketplace/products/{slug}/metrics/         # Specific product metrics
```

---

## 📋 Complete Endpoint List with HTTP Methods

### Categories
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/categories/` | List all categories |
| `GET` | `/categories/{id}/` | Get category details |

### Products
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products/` | List products |
| `POST` | `/products/` | Create product |
| `GET` | `/products/{slug}/` | Get product |
| `PUT` | `/products/{slug}/` | Update product |
| `PATCH` | `/products/{slug}/` | Partial update |
| `DELETE` | `/products/{slug}/` | Delete product |

### Products > Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products/search/` | Search products |
| `GET` | `/products/autocomplete/` | Autocomplete |
| `GET` | `/products/filters/` | Get filters |

### Products > Reviews
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products/{slug}/reviews/` | List reviews |
| `POST` | `/products/{slug}/reviews/` | Create review |
| `GET` | `/products/{slug}/reviews/{id}/` | Get review |
| `PUT` | `/products/{slug}/reviews/{id}/` | Update review |
| `DELETE` | `/products/{slug}/reviews/{id}/` | Delete review |

### Products > Images
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products/{slug}/images/` | List images |
| `POST` | `/products/{slug}/images/` | Upload image |
| `GET` | `/products/{slug}/images/{id}/` | Get image |
| `PUT` | `/products/{slug}/images/{id}/` | Update image |
| `DELETE` | `/products/{slug}/images/{id}/` | Delete image |

### Products > Metrics
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products/metrics/` | All product metrics |
| `GET` | `/products/{slug}/metrics/` | Specific product metrics |

### Cart
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/cart/` | Get cart |
| `POST` | `/cart/add/` | Add item |
| `PUT` | `/cart/update/` | Update item |
| `DELETE` | `/cart/remove/` | Remove item |
| `DELETE` | `/cart/` | Clear cart |
| `GET` | `/cart/validate/` | Validate cart |

### Orders
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/orders/` | List orders |
| `POST` | `/orders/` | Create order |
| `GET` | `/orders/{id}/` | Get order |
| `POST` | `/orders/{id}/cancel/` | Cancel order |

### Sellers
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sellers/{id}/` | Get seller profile |
| `GET` | `/sellers/{id}/products/` | Seller's products |

### Internal
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/internal/products/{id}/` | Internal product info |
| `GET` | `/internal/orders/{id}/` | Internal order info |

### Monitoring
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/metrics/` | Prometheus metrics |

---

## 🎨 Swagger UI Organization

In Swagger UI (http://localhost:8000/api/docs/), endpoints are organized into these groups:

```
📦 Marketplace API
├── 📂 Categories
│   └── List categories, Get category details
│
├── 📂 Products
│   ├── List products, Create product, Get/Update/Delete product
│   │
│   ├── 📂 Search & Filters
│   │   └── Search, Autocomplete, Get filters
│   │
│   ├── 📂 Reviews
│   │   └── List/Create/Update/Delete reviews (nested under products)
│   │
│   ├── 📂 Images
│   │   └── Manage product images (nested under products)
│   │
│   └── 📂 Metrics
│       └── Product analytics and metrics
│
├── 📂 Cart
│   └── Get cart, Add/Update/Remove items, Validate
│
├── 📂 Orders
│   └── List orders, Create order, Get/Cancel order
│
├── 📂 Sellers
│   └── Seller profiles and products
│
├── 📂 User Profiles
│   └── User profile management
│
├── 📂 Internal APIs
│   └── Service-to-service endpoints (not public)
│
└── 📂 Monitoring
    └── Prometheus metrics
```

---

## 🔄 Migration Guide

If you're updating from the old structure:

### Reviews
**Old:**
```bash
GET  /api/marketplace/reviews/?product_id=uuid
POST /api/marketplace/reviews/
```

**New:**
```bash
GET  /api/marketplace/products/{slug}/reviews/
POST /api/marketplace/products/{slug}/reviews/
```

### Metrics
**Old:**
```bash
GET /api/marketplace/metrics/
```

**New:**
```bash
GET /api/marketplace/products/metrics/              # All products
GET /api/marketplace/products/{slug}/metrics/       # Specific product
```

### Seller Products
**New Addition:**
```bash
GET /api/marketplace/sellers/{id}/products/         # List seller's products
```

---

## 💡 Best Practices

### 1. **Use Nested URLs for Related Resources**
```bash
✅ /products/{slug}/reviews/           # Reviews belong to a product
✅ /products/{slug}/images/            # Images belong to a product
❌ /reviews/?product_id=uuid           # Not clear relationship
```

### 2. **Use Plural Resource Names**
```bash
✅ /products/
✅ /orders/
✅ /categories/
❌ /product/
```

### 3. **Use HTTP Methods Correctly**
```bash
GET    - Retrieve resource(s)
POST   - Create new resource
PUT    - Update entire resource
PATCH  - Partial update
DELETE - Remove resource
```

### 4. **Use Descriptive Custom Actions**
```bash
✅ POST /orders/{id}/cancel/           # Clear action
✅ POST /cart/add/                     # Clear action
✅ GET  /cart/validate/                # Clear action
❌ POST /orders/{id}/action/           # Unclear
```

---

## 🚀 Using the New Structure

### Example: Working with Product Reviews

```bash
# 1. Get a product
GET /api/marketplace/products/iphone-15-pro/

# 2. List reviews for that product
GET /api/marketplace/products/iphone-15-pro/reviews/

# 3. Create a review for that product
POST /api/marketplace/products/iphone-15-pro/reviews/
{
  "rating": 5,
  "title": "Great product!",
  "comment": "Amazing phone"
}

# 4. Update a review
PUT /api/marketplace/products/iphone-15-pro/reviews/42/
{
  "rating": 4,
  "comment": "Updated review"
}

# 5. Delete a review
DELETE /api/marketplace/products/iphone-15-pro/reviews/42/
```

---

## 📊 URL Structure Benefits

✅ **Clear hierarchy** - Parent-child relationships obvious
✅ **RESTful** - Follows REST conventions
✅ **Discoverable** - Easy to guess URL patterns
✅ **Organized** - Logical grouping in Swagger UI
✅ **Maintainable** - Easy to understand and extend
✅ **Scalable** - Can add new nested resources easily

---

**View the interactive API documentation:** http://localhost:8000/api/docs/ 🚀
