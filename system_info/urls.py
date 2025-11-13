from django.urls import path

from . import views

app_name = "system_info"

urlpatterns = [
    # S3 image proxy endpoints
    path("s3-images/<path:path>/", views.s3_image_proxy, name="s3_image_proxy"),
    path("s3-images/<path:path>/info/", views.s3_image_info, name="s3_image_info"),
]
