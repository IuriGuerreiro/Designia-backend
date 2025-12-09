"""
Internal API URL Configuration

Routes for service-to-service communication.
These endpoints are NOT exposed through Kong Gateway.

Security:
- No authentication required (internal network trust)
- Should only be accessible within Docker network
- Configure firewall/network policies to restrict access
"""

from django.urls import path

from authentication.api.views import internal_views

# Internal API - NOT exposed through gateway
urlpatterns = [
    # Get user by ID
    path("users/<uuid:user_id>/", internal_views.internal_get_user, name="internal_get_user"),
    # Validate JWT token
    path("validate-token/", internal_views.internal_validate_token, name="internal_validate_token"),
    # Batch get users
    path("users/batch/", internal_views.internal_batch_get_users, name="internal_batch_get_users"),
    # Check email existence
    path("check-email/<str:email>/", internal_views.internal_check_user_email, name="internal_check_email"),
]
