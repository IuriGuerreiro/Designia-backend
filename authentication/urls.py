from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("register/", views.RegisterAPIView.as_view(), name="register"),
    path("login/", views.LoginAPIView.as_view(), name="login"),
    path("login/verify-2fa/", views.login_verify_2fa, name="login_verify_2fa"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("profile/", views.ProfileUpdateView.as_view(), name="profile"),
    path("verify-email/", views.verify_email, name="verify_email"),
    path("resend-verification/", views.resend_verification_email, name="resend_verification"),
    path("check-rate-limit/", views.check_email_rate_limit, name="check_email_rate_limit"),
    path("resend-2fa-code/", views.resend_2fa_code, name="resend_2fa_code"),
    # Google OAuth endpoints (YummiAI style)
    path("google/login/", views.google_login, name="google_login"),
    path("google/register/", views.google_register, name="google_register"),
    path("google-oauth/", views.google_oauth, name="google_oauth"),  # Legacy endpoint
    # 2FA endpoints
    path("2fa/toggle/", views.toggle_2fa, name="toggle_2fa"),
    path("2fa/verify/", views.verify_2fa, name="verify_2fa"),
    path("2fa/status/", views.get_2fa_status, name="get_2fa_status"),
    # Password setup endpoints (OAuth users only)
    path("password/request/", views.request_password_setup, name="request_password_setup"),
    path("password/set/", views.set_password_with_2fa, name="set_password_with_2fa"),
    # Password reset endpoints (all users)
    path("password/reset/request/", views.request_password_reset, name="request_password_reset"),
    path("password/reset/", views.reset_password_with_2fa, name="reset_password_with_2fa"),
    # Language preference
    path("change-language/", views.change_language, name="change_language"),
    # Public user profile
    path("users/<int:pk>/", views.PublicProfileDetailView.as_view(), name="public_profile_detail"),
    # Profile picture endpoints
    path("profile/picture/upload/", views.upload_profile_picture, name="upload_profile_picture"),
    path("profile/picture/delete/", views.delete_profile_picture, name="delete_profile_picture"),
    # Seller application endpoints
    path("", include("authentication.seller_urls")),
]
