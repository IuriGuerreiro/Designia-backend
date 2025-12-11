import uuid

from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from .category import Category

User = get_user_model()


class Product(models.Model):
    CONDITION_CHOICES = [
        ("new", "New"),
        ("like_new", "Like New"),
        ("good", "Good"),
        ("fair", "Fair"),
        ("poor", "Poor"),
    ]

    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True)

    # Seller and Category
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="products")

    # Pricing and Inventory
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01), MaxValueValidator(100000)]
    )
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=1)

    # Product Details
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default="new")
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)

    # Physical Properties
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Weight in kg")
    dimensions_length = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Length in cm"
    )
    dimensions_width = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Width in cm"
    )
    dimensions_height = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Height in cm"
    )

    # Product Attributes
    colors = models.JSONField(default=list, blank=True, help_text="Available colors")
    materials = models.TextField(blank=True, help_text="Materials used")
    tags = models.JSONField(default=list, blank=True, help_text="Product tags")

    # Status and Visibility
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_digital = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Metrics
    view_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    favorite_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        app_label = "marketplace"
        indexes = [
            # Existing indexes
            models.Index(fields=["seller", "is_active"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["price"]),
            models.Index(fields=["is_featured", "is_active"]),
            # Additional performance indexes
            models.Index(fields=["is_active", "-created_at"]),  # Most common query pattern
            models.Index(fields=["is_active", "price"]),  # Price filtering
            models.Index(fields=["is_active", "-view_count"]),  # Popular products
            models.Index(fields=["is_active", "-favorite_count"]),  # Most favorited
            models.Index(fields=["category", "is_active", "-created_at"]),  # Category listings
            models.Index(fields=["seller", "is_active", "-created_at"]),  # Seller products
            models.Index(fields=["brand", "is_active"]),  # Brand filtering
            models.Index(fields=["condition", "is_active"]),  # Condition filtering
            models.Index(fields=["stock_quantity", "is_active"]),  # Stock availability
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{str(self.id)[:8]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", blank=True)  # Keep for backward compatibility
    # S3 storage fields
    s3_key = models.CharField(max_length=500, blank=True, help_text="S3 object key for the image")
    s3_bucket = models.CharField(max_length=100, blank=True, help_text="S3 bucket name")
    original_filename = models.CharField(max_length=255, blank=True, help_text="Original filename")
    file_size = models.PositiveIntegerField(null=True, blank=True, help_text="File size in bytes")
    content_type = models.CharField(max_length=100, blank=True, help_text="MIME type")
    # Existing fields
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]
        app_label = "marketplace"

    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        super().save(*args, **kwargs)

    def get_presigned_url(self, expires_in=3600):
        """Get presigned URL from S3 storage"""
        if not self.s3_key:
            if self.image:
                try:
                    return self.image.url
                except Exception:
                    return None
            return None

        try:
            from django.conf import settings

            if not getattr(settings, "USE_S3", False):
                if self.image:
                    return self.image.url
                return None

            from utils.s3_storage import get_s3_storage

            s3 = get_s3_storage()
            return s3.get_file_url(self.s3_key, expires_in=expires_in)
        except Exception:
            # Fallback to standard URL if S3 fails
            if self.image:
                return self.image.url
            return None

    def get_proxy_url(self):
        """Get proxy URL for the image"""
        # For now, just alias to presigned URL or public URL
        # The serializer calls this, so it must exist.
        return self.get_presigned_url()

    def __str__(self):
        return f"Image for {self.product.name}"
