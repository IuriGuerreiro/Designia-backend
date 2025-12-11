import uuid

from django.contrib.auth import get_user_model
from django.db import models

from marketplace.catalog.domain.models.catalog import Product

User = get_user_model()


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
        app_label = "marketplace"

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

    class Meta:
        app_label = "marketplace"

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
        app_label = "marketplace"

    def __str__(self):
        return f"Shipping for {self.seller.username} in order {str(self.order.id)[:8]}"
