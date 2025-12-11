"""
Internal API URL Configuration - Marketplace

Routes for service-to-service communication.
These endpoints are NOT exposed through Kong Gateway.

Security:
- No authentication required (internal network trust)
- Should only be accessible within Docker network
- Configure firewall/network policies to restrict access

Use Cases:
- Payment service checking product prices
- Notification service getting order details
- Analytics service tracking metrics
"""

from django.urls import path

from marketplace.api.views import internal_views

# Internal API - NOT exposed through gateway
urlpatterns = [
    # Get product info (for Payment, Notification services)
    path(
        "products/<uuid:product_id>/",
        internal_views.internal_get_product,
        name="internal_marketplace_get_product",
    ),
    # Get order info (for Payment webhooks, Analytics)
    path(
        "orders/<uuid:order_id>/",
        internal_views.internal_get_order,
        name="internal_marketplace_get_order",
    ),
]
