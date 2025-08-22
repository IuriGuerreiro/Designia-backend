from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet, ProductViewSet, ProductImageViewSet, ProductReviewViewSet,
    CartViewSet, OrderViewSet, ProductMetricsViewSet, UserProfileViewSet
)

# Create the main router
router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'reviews', ProductReviewViewSet, basename='review')
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'metrics', ProductMetricsViewSet, basename='metrics')
router.register(r'profiles', UserProfileViewSet, basename='profile')

app_name = 'marketplace'

urlpatterns = [
    # Main API routes
    path('', include(router.urls)),
    
    # Nested product routes (manual routing)
    path('products/<slug:product_slug>/images/', 
         ProductImageViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='product-images-list'),
    path('products/<slug:product_slug>/images/<int:pk>/', 
         ProductImageViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), 
         name='product-images-detail'),
    path('products/<slug:product_slug>/reviews/', 
         ProductReviewViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='product-reviews-list'),
    path('products/<slug:product_slug>/reviews/<int:pk>/', 
         ProductReviewViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), 
         name='product-reviews-detail'),
]