from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils import timezone
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
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01), MaxValueValidator(100000)])
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
            # Existing indexes
            models.Index(fields=['seller', 'is_active']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['created_at']),
            models.Index(fields=['price']),
            models.Index(fields=['is_featured', 'is_active']),
            # Additional performance indexes
            models.Index(fields=['is_active', '-created_at']),  # Most common query pattern
            models.Index(fields=['is_active', 'price']),  # Price filtering
            models.Index(fields=['is_active', '-view_count']),  # Popular products
            models.Index(fields=['is_active', '-favorite_count']),  # Most favorited
            models.Index(fields=['category', 'is_active', '-created_at']),  # Category listings
            models.Index(fields=['seller', 'is_active', '-created_at']),  # Seller products
            models.Index(fields=['brand', 'is_active']),  # Brand filtering
            models.Index(fields=['condition', 'is_active']),  # Condition filtering
            models.Index(fields=['stock_quantity', 'is_active']),  # Stock availability
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
        indexes = [
            models.Index(fields=['user', 'product']),  # For favorite checks
            models.Index(fields=['product']),  # For product's favorite list
            models.Index(fields=['user']),  # For user's favorites
            models.Index(fields=['created_at']),  # For ordering
        ]

    def __str__(self):
        return f"{self.user.username} favorited {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),  # Default status - cannot be changed manually
        ('payment_confirmed', 'Payment Confirmed'),  # Set by Stripe webhook when payment succeeds
        ('awaiting_shipment', 'Awaiting Shipment'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('failed_refund', 'Failed Refund'),
        ('partial_refund', 'Partial Refund'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    
    # Order Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_payment')
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
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cancelled_orders')  # Who cancelled the order
    cancelled_at = models.DateTimeField(null=True, blank=True)  # When the order was cancelled
    processed_at = models.DateTimeField(null=True, blank=True)  # When order moved to processing
    
    # Payment and locking
    is_locked = models.BooleanField(default=False)  # Lock order from modification during/after payment
    locked_at = models.DateTimeField(null=True, blank=True)  # When the order was locked
    payment_initiated_at = models.DateTimeField(null=True, blank=True)  # When payment was initiated

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {str(self.id)[:8]} by {self.buyer.username}"
    
    def lock_order(self):
        """Lock the order to prevent modifications during/after payment"""
        if not self.is_locked:
            self.is_locked = True
            self.locked_at = timezone.now()
            self.save(update_fields=['is_locked', 'locked_at'])
    
    def can_be_modified(self):
        """Check if order can be modified (not locked and payment not initiated)"""
        return not self.is_locked and self.payment_status in ['pending']
    
    def initiate_payment(self):
        """Mark payment as initiated and lock the order"""
        if self.can_be_modified():
            self.payment_status = 'processing'
            self.status = 'awaiting_payment'
            self.payment_initiated_at = timezone.now()
            self.lock_order()
            self.save(update_fields=['payment_status', 'status', 'payment_initiated_at'])
            return True
        return False
    
    def confirm_payment(self):
        """Confirm successful payment"""
        self.payment_status = 'paid'
        self.status = 'confirmed'
        self.save(update_fields=['payment_status', 'status'])


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


class OrderShipping(models.Model):
    """Tracking information for each seller in an order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='shipping_info')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_shipments')
    
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
        unique_together = ['order', 'seller']  # One shipping record per seller per order
        ordering = ['-created_at']

    def __str__(self):
        return f"Shipping for {self.seller.username} in order {str(self.order.id)[:8]}"


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shopping Cart"
        verbose_name_plural = "Shopping Carts"

    def __str__(self):
        return f"Cart for {self.user.username}"

    @property
    def total_items(self):
        return self.items.aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def total_amount(self):
        from decimal import Decimal
        total = Decimal('0')
        for item in self.items.all():
            total += item.quantity * item.product.price
        return total
    
    def clear_items(self):
        """Clear all items from cart"""
        self.items.all().delete()
    
    @classmethod
    def get_or_create_cart(cls, user):
        """Get or create user's unique cart"""
        cart, created = cls.objects.get_or_create(user=user)
        return cart


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
    
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Metrics for {self.product.name}"
    
    def update_conversion_rates(self):
        """
        Update calculated conversion rate fields.
        This method is now a no-op since rate fields have been removed.
        Kept for backwards compatibility with existing tracking code.
        """
        # No-op: Rate fields have been removed from the model
        pass
    
    @property
    def view_to_click_rate(self):
        """Calculate view-to-click conversion rate on-demand"""
        if self.total_views == 0:
            return 0.0
        return (self.total_clicks / self.total_views) * 100
    
    @property 
    def click_to_cart_rate(self):
        """Calculate click-to-cart conversion rate on-demand"""
        if self.total_clicks == 0:
            return 0.0
        return (self.total_cart_additions / self.total_clicks) * 100
    
    @property
    def cart_to_purchase_rate(self):
        """Calculate cart-to-purchase conversion rate on-demand"""
        if self.total_cart_additions == 0:
            return 0.0
        return (self.total_sales / self.total_cart_additions) * 100
    
    @property
    def overall_conversion_rate(self):
        """Calculate overall view-to-purchase conversion rate on-demand"""
        if self.total_views == 0:
            return 0.0
        return (self.total_sales / self.total_views) * 100