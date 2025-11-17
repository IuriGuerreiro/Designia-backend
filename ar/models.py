from django.conf import settings
from django.db import models

from marketplace.models import Product


class ProductARModel(models.Model):
    """
    Stores metadata about a single 3D model file attached to a product.
    Only one record exists per product (OneToOne relationship).
    """

    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="ar_model")
    s3_key = models.CharField(max_length=512)
    s3_bucket = models.CharField(max_length=128)
    original_filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_ar_models",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_download_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Product 3D Model"
        verbose_name_plural = "Product 3D Models"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"3D model for {self.product.name}"


class ProductARModelDownload(models.Model):
    """
    Tracks when a user downloads a 3D model and where it was stored locally.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ar_model_downloads",
    )
    product_model = models.ForeignKey(
        ProductARModel,
        on_delete=models.CASCADE,
        related_name="downloads",
    )
    local_path = models.CharField(max_length=1024, blank=True, default="")
    file_name = models.CharField(max_length=255, blank=True, default="")
    file_size = models.BigIntegerField(null=True, blank=True)
    platform = models.CharField(max_length=64, blank=True)
    app_version = models.CharField(max_length=64, blank=True)
    device_info = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product 3D Model Download"
        verbose_name_plural = "Product 3D Model Downloads"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file_name} - {self.user}"
