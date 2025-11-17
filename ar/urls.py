from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductARModelDownloadViewSet, ProductARModelViewSet

router = DefaultRouter()
router.register(r"models", ProductARModelViewSet, basename="ar-model")
router.register(r"downloads", ProductARModelDownloadViewSet, basename="ar-model-download")

app_name = "ar"

urlpatterns = [
    path("", include(router.urls)),
]
