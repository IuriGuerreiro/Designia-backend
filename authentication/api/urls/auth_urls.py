from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from authentication.api.views import (
    AccountStatusView,
    Disable2FAView,
    Enable2FAView,
    GoogleLoginView,
    LoginAPIView,
    ProfilePictureUploadView,
    ProfileUpdateView,
    PublicProfileDetailView,
    RegisterAPIView,
    ResendVerificationView,
    SellerApplicationAdminView,
    SellerApplicationCreateView,
    Send2FACodeView,
    TwoFactorLoginVerifyView,
    VerifyEmailView,
    health_views,
    metrics_views,
)


urlpatterns = [
    # Auth
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend_verification"),
    path("google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("login/verify-2fa/", TwoFactorLoginVerifyView.as_view(), name="login_verify_2fa"),
    # 2FA Management
    path("2fa/send-code/", Send2FACodeView.as_view(), name="send_2fa_code"),
    path("2fa/enable/", Enable2FAView.as_view(), name="enable_2fa"),
    path("2fa/disable/", Disable2FAView.as_view(), name="disable_2fa"),
    path("account/status/", AccountStatusView.as_view(), name="account_status"),
    # Profile
    path("profile/", ProfileUpdateView.as_view(), name="profile"),
    path("profile/picture/upload/", ProfilePictureUploadView.as_view(), name="upload_profile_picture"),
    path("profile/picture/delete/", ProfilePictureUploadView.as_view(), name="delete_profile_picture"),
    path("users/<uuid:pk>/", PublicProfileDetailView.as_view(), name="public_profile_detail"),
    # Seller
    path("seller/apply/", SellerApplicationCreateView.as_view(), name="seller_apply"),
    path("seller/application/status/", SellerApplicationCreateView.as_view(), name="seller_application_status"),
    path(
        "admin/seller/applications/<int:pk>/",
        SellerApplicationAdminView.as_view(),
        name="admin_seller_application_update",
    ),
    # Phase 3: Observability & Health
    # Prometheus metrics endpoint (for scraping)
    path("metrics/", metrics_views.metrics, name="metrics"),
    # Kubernetes health probes
    path("health/live/", health_views.health_live, name="health_live"),
    path("health/ready/", health_views.health_ready, name="health_ready"),
]
