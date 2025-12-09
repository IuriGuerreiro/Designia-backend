from django.urls import include, path

urlpatterns = [
    path("", include("authentication.api.urls.auth_urls")),
]
