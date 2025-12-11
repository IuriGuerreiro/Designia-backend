from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api.views import prometheus_metrics
from .views import (
    CartViewSet,
    CategoryViewSet,
    OrderViewSet,
    ProductImageViewSet,
    ProductMetricsViewSet,
    ProductViewSet,
    ReviewViewSet,
    SearchViewSet,
    UserProfileViewSet,
    seller_profile,
)

# Create routers for different resource groups
router = DefaultRouter()

# Categories - Top level
router.register(r"categories", CategoryViewSet, basename="category")

# Products - Main resource
router.register(r"products", ProductViewSet, basename="product")

# Cart - Top level resource
router.register(r"cart", CartViewSet, basename="cart")

# Orders - Top level resource
router.register(r"orders", OrderViewSet, basename="order")

# User Profiles - Top level resource
router.register(r"profiles", UserProfileViewSet, basename="profile")

app_name = "marketplace"

urlpatterns = [
    # ==================== CATEGORIES ====================
    # Handled by router: /categories/
    # ==================== PRODUCTS ====================
    # Product listing and CRUD - Handled by router: /products/
    # Product Search & Filters
    path("products/search/", SearchViewSet.as_view({"get": "search"}), name="product-search"),
    path("products/autocomplete/", SearchViewSet.as_view({"get": "autocomplete"}), name="product-autocomplete"),
    path("products/filters/", SearchViewSet.as_view({"get": "filters"}), name="product-filters"),
    # Product Images (nested under specific product)
    path(
        "products/<slug:product_slug>/images/",
        ProductImageViewSet.as_view({"get": "list", "post": "create"}),
        name="product-images-list",
    ),
    path(
        "products/<slug:product_slug>/images/<int:pk>/",
        ProductImageViewSet.as_view({"get": "retrieve", "put": "update", "delete": "destroy"}),
        name="product-images-detail",
    ),
    # Product Reviews (nested under specific product)
    path(
        "products/<slug:product_slug>/reviews/",
        ReviewViewSet.as_view({"get": "list", "post": "create"}),
        name="product-reviews-list",
    ),
    path(
        "products/<slug:product_slug>/reviews/<int:pk>/",
        ReviewViewSet.as_view({"get": "retrieve", "put": "update", "delete": "destroy"}),
        name="product-reviews-detail",
    ),
    # Product Metrics (Analytics for sellers)
    path(
        "products/metrics/",
        ProductMetricsViewSet.as_view({"get": "list"}),
        name="product-metrics",
    ),
    path(
        "products/<slug:product_slug>/metrics/",
        ProductMetricsViewSet.as_view({"get": "retrieve"}),
        name="product-metrics-detail",
    ),
    # ==================== CART ====================
    # Handled by router: /cart/
    # Note: CartViewSet has custom actions: add, update, remove, validate
    # ==================== ORDERS ====================
    # Handled by router: /orders/
    # Note: OrderViewSet has custom actions: cancel
    # ==================== SELLERS ====================
    path("sellers/<int:seller_id>/", seller_profile, name="seller-profile"),
    path(
        "sellers/<int:seller_id>/products/",
        ProductViewSet.as_view({"get": "list"}),
        name="seller-products",
    ),
    # ==================== USER PROFILES ====================
    # Handled by router: /profiles/
    # ==================== METRICS (Prometheus) ====================
    path("metrics/", prometheus_metrics.marketplace_prometheus_metrics, name="marketplace-metrics"),
    # Include router URLs
    path("", include(router.urls)),
]
