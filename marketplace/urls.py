from django.urls import path
from rest_framework.routers import DefaultRouter

from marketplace.api.views import internal_views
from marketplace.cart.api.views.cart_views import CartViewSet
from marketplace.catalog.api.views.category_views import CategoryViewSet
from marketplace.catalog.api.views.image_views import ProductImageViewSet
from marketplace.catalog.api.views.metric_views import ProductMetricsViewSet
from marketplace.catalog.api.views.product_views import ProductViewSet
from marketplace.catalog.api.views.profile_views import UserProfileViewSet, seller_profile
from marketplace.catalog.api.views.review_views import ReviewViewSet
from marketplace.catalog.api.views.search_views import SearchViewSet
from marketplace.ordering.api.views.order_views import OrderViewSet

from .api.views import prometheus_metrics


# Create the main router
router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register(r"reviews", ReviewViewSet, basename="review")
router.register(r"cart", CartViewSet, basename="cart")
router.register(r"orders", OrderViewSet, basename="order")
router.register(r"metrics", ProductMetricsViewSet, basename="metrics")
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
    path("internal/orders/<uuid:order_id>/", internal_views.internal_get_order, name="internal-get-order"),
    # Manual Category URLs under /products/
    path(
        "products/categories/",
        CategoryViewSet.as_view({"get": "list"}),
        name="product-category-list",
    ),
    path(
        "products/categories/<slug:slug>/",
        CategoryViewSet.as_view({"get": "retrieve"}),
        name="product-category-detail",
    ),
    # Prometheus metrics endpoint
    path("metrics/", prometheus_metrics.marketplace_prometheus_metrics, name="marketplace-metrics"),
]

urlpatterns += router.urls
