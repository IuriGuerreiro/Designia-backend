import uuid

from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="subcategories")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


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

    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    helpful_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["product", "reviewer"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.product.name}"


class ProductReviewHelpful(models.Model):
    review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name="helpful_votes")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="helpful_reviews")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["review", "user"]

    def __str__(self):
        return f"{self.user.username} found review {self.review.id} helpful"


class ProductFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "product"]
        indexes = [
            models.Index(fields=["user", "product"]),  # For favorite checks
            models.Index(fields=["product"]),  # For product's favorite list
            models.Index(fields=["user"]),  # For user's favorites
            models.Index(fields=["created_at"]),  # For ordering
        ]

    def __str__(self):
        return f"{self.user.username} favorited {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending_payment", "Pending Payment"),  # Default status - cannot be changed manually
        ("payment_confirmed", "Payment Confirmed"),  # Set by Stripe webhook when payment succeeds
        ("awaiting_shipment", "Awaiting Shipment"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
        ("failed_refund", "Failed Refund"),
        ("partial_refund", "Partial Refund"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")

    # Order Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending_payment")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending")

    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Shipping Information
    shipping_address = models.JSONField()
    tracking_number = models.CharField(max_length=100, blank=True)
    shipping_carrier = models.CharField(max_length=100, blank=True)
    carrier_code = models.CharField(max_length=100, blank=True)  # CTT DY08912401385471 style codes

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Notes
    buyer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)  # Reason for order cancellation
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="cancelled_orders"
    )  # Who cancelled the order
    cancelled_at = models.DateTimeField(null=True, blank=True)  # When the order was cancelled
    processed_at = models.DateTimeField(null=True, blank=True)  # When order moved to processing

    # Payment and locking
    is_locked = models.BooleanField(default=False)  # Lock order from modification during/after payment
    locked_at = models.DateTimeField(null=True, blank=True)  # When the order was locked
    payment_initiated_at = models.DateTimeField(null=True, blank=True)  # When payment was initiated

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {str(self.id)[:8]} by {self.buyer.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sold_items")

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Product snapshot at time of purchase
    product_name = models.CharField(max_length=200)
    product_description = models.TextField()
    product_image = models.URLField(max_length=2000, blank=True)

    def __str__(self):
        return f"{self.quantity}x {self.product_name} in order {str(self.order.id)[:8]}"


class OrderShipping(models.Model):
    """Tracking information for each seller in an order"""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shipping_info")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="order_shipments")

    # Tracking Information
    tracking_number = models.CharField(max_length=100, blank=True)
    shipping_carrier = models.CharField(max_length=100, blank=True)  # CTT, DHL, UPS, etc.
    carrier_code = models.CharField(max_length=100, blank=True)  # CTT DY08912401385471 style codes

    # Status and Timestamps
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["order", "seller"]  # One shipping record per seller per order
        ordering = ["-created_at"]

    def __str__(self):
        return f"Shipping for {self.seller.username} in order {str(self.order.id)[:8]}"


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shopping Cart"
        verbose_name_plural = "Shopping Carts"

    @classmethod
    def get_or_create_cart(cls, user):
        """Get existing cart or create a new one for the user."""
        cart, _ = cls.objects.get_or_create(user=user)
        return cart

    def __str__(self):
        return f"Cart for {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["cart", "product"]

    @property
    def total_price(self):
        return self.quantity * self.product.price

    def __str__(self):
        return f"{self.quantity}x {self.product.name} in {self.cart.user.username}'s cart"


class ProductMetrics(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="metrics")
    total_views = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    total_favorites = models.PositiveIntegerField(default=0)
    total_cart_additions = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Metrics for {self.product.name}"
