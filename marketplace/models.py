from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
import uuid

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('like_new', 'Like New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]

    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    short_description = models.CharField(max_length=300, blank=True)
    
    # Seller and Category
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    
    # Pricing and Inventory
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=1)
    
    # Product Details
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    
    # Physical Properties
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Weight in kg")
    dimensions_length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Length in cm")
    dimensions_width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Width in cm")
    dimensions_height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Height in cm")
    
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
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'is_active']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['created_at']),
            models.Index(fields=['price']),
            models.Index(fields=['is_featured', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{str(self.id)[:8]}")
        super().save(*args, **kwargs)

    @property
    def is_on_sale(self):
        return self.original_price and self.original_price > self.price

    @property
    def discount_percentage(self):
        if self.is_on_sale:
            return int(((self.original_price - self.price) / self.original_price) * 100)
        return 0

    @property
    def average_rating(self):
        reviews = self.reviews.filter(is_active=True)
        if reviews.exists():
            return reviews.aggregate(models.Avg('rating'))['rating__avg']
        return 0

    @property
    def review_count(self):
        return self.reviews.filter(is_active=True).count()

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['product', 'reviewer']
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.product.name}"


class ProductFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'product']

    def __str__(self):
        return f"{self.user.username} favorited {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('partial_refund', 'Partial Refund'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    
    # Order Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
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
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Notes
    buyer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {str(self.id)[:8]} by {self.buyer.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sold_items')
    
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Product snapshot at time of purchase
    product_name = models.CharField(max_length=200)
    product_description = models.TextField()
    product_image = models.URLField(blank=True)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity}x {self.product_name} in order {str(self.order.id)[:8]}"


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.username}"

    @property
    def total_items(self):
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def total_amount(self):
        total = 0
        for item in self.items.all():
            total += item.quantity * item.product.price
        return total


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['cart', 'product']

    def __str__(self):
        return f"{self.quantity}x {self.product.name} in {self.cart.user.username}'s cart"

    @property
    def total_price(self):
        return self.quantity * self.product.price


class ProductMetrics(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='metrics')
    total_views = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    total_favorites = models.PositiveIntegerField(default=0)
    total_cart_additions = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Conversion metrics
    view_to_click_rate = models.FloatField(default=0)
    click_to_cart_rate = models.FloatField(default=0)
    cart_to_purchase_rate = models.FloatField(default=0)
    
    last_updated = models.DateTimeField(auto_now=True)

    def update_conversion_rates(self):
        self.view_to_click_rate = (self.total_clicks / self.total_views * 100) if self.total_views > 0 else 0
        self.click_to_cart_rate = (self.total_cart_additions / self.total_clicks * 100) if self.total_clicks > 0 else 0
        self.cart_to_purchase_rate = (self.total_sales / self.total_cart_additions * 100) if self.total_cart_additions > 0 else 0
        self.save()

    def __str__(self):
        return f"Metrics for {self.product.name}"