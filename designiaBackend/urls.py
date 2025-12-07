"""
URL configuration for designiaBackend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from ar.admin_views import ProductARModelAdminDownloadView, ProductARModelAdminListView

urlpatterns = [
    path("admin/", admin.site.urls),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # API endpoints
    path("api/auth/", include("authentication.urls")),
    path("api/marketplace/", include("marketplace.urls")),
    path("api/activity/", include("activity.urls")),
    path("api/payments/", include("payment_system.urls", namespace="payment_system")),
    path("api/chat/", include("chat.urls")),
    path("api/system/", include("system_info.urls")),
    path("api/ar/", include("ar.urls")),
    path("admin/ar/models/", ProductARModelAdminListView.as_view(), name="admin-ar-models"),
    path(
        "admin/ar/models/<int:pk>/download/",
        ProductARModelAdminDownloadView.as_view(),
        name="admin-ar-model-download",
    ),
]

# Serve media files during development

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
