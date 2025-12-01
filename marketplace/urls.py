from django.urls import include, path
from rest_framework.routers import DefaultRouter

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

# Create the main router
router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")
router.register(r"reviews", ReviewViewSet, basename="review")
router.register(r"cart", CartViewSet, basename="cart")
router.register(r"orders", OrderViewSet, basename="order")
router.register(r"metrics", ProductMetricsViewSet, basename="metrics")
router.register(r"profiles", UserProfileViewSet, basename="profile")

app_name = "marketplace"

urlpatterns = [
    # Search endpoints (override ProductViewSet search)
    path("products/search/", SearchViewSet.as_view({"get": "search"}), name="product-search"),
    path("products/autocomplete/", SearchViewSet.as_view({"get": "autocomplete"}), name="product-autocomplete"),
    path("products/filters/", SearchViewSet.as_view({"get": "filters"}), name="product-filters"),
    # Main API routes
    path("", include(router.urls)),
    # Nested product routes (manual routing)
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
    # Seller profile route
    path("sellers/<int:seller_id>/", seller_profile, name="seller-profile"),
]
