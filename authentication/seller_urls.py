from django.urls import path

from . import seller_views

urlpatterns = [
    # User endpoints
    path("seller/apply/", seller_views.apply_to_become_seller, name="apply_to_become_seller"),
    path("seller/application/status/", seller_views.seller_application_status, name="seller_application_status"),
    path("seller/application/", seller_views.SellerApplicationDetailView.as_view(), name="seller_application_detail"),
    path("user/role/", seller_views.user_role_info, name="user_role_info"),
    # Admin endpoints
    path(
        "admin/seller/applications/",
        seller_views.SellerApplicationListView.as_view(),
        name="admin_seller_applications",
    ),
    path(
        "admin/seller/applications/<int:pk>/",
        seller_views.SellerApplicationAdminUpdateView.as_view(),
        name="admin_seller_application_update",
    ),
    path("admin/seller/approve/<int:application_id>/", seller_views.admin_approve_seller, name="admin_approve_seller"),
    path("admin/seller/reject/<int:application_id>/", seller_views.admin_reject_seller, name="admin_reject_seller"),
]
