from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductARModelViewSet

router = DefaultRouter()
router.register(r"models", ProductARModelViewSet, basename="ar-model")

app_name = "ar"

urlpatterns = [
    path("", include(router.urls)),
]
