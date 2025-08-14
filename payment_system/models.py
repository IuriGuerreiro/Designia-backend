from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid

User = get_user_model()


class PaymentTracker(models.Model):
    """Simple payment tracking table to associate Stripe payment IDs with orders"""
    
    TRANSACTION_TYPE_CHOICES = [
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('partial_refund', 'Partial Refund'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded'),
    ]
    
    # Basic identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_refund_id = models.CharField(max_length=255, blank=True, db_index=True)
    
    # Relations
    order = models.ForeignKey(
        'marketplace.Order', 
        on_delete=models.CASCADE,
        related_name='payment_trackers',
        db_index=True
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='payment_trackers',
        db_index=True
    )
    
    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, default='payment')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Optional tracking fields
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        stripe_id = self.stripe_payment_intent_id or self.stripe_refund_id or 'No Stripe ID'
        return f"{self.transaction_type.title()}: {stripe_id} - ${self.amount} [{self.status}]"
    
    class Meta:
        db_table = 'payment_trackers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['stripe_refund_id']),
            models.Index(fields=['order', 'transaction_type']),
            models.Index(fields=['user', 'status']),
        ]


class WebhookEvent(models.Model):
    """Log of Stripe webhook events for debugging and tracking"""
    
    EVENT_STATUS_CHOICES = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('ignored', 'Ignored'),
    ]
    
    # Event details
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    
    # Processing status
    status = models.CharField(max_length=20, choices=EVENT_STATUS_CHOICES, default='received')
    processing_attempts = models.IntegerField(default=0)
    last_processing_error = models.TextField(blank=True)
    
    # Event data
    event_data = models.JSONField()
    
    # Optional relation to payment tracker
    payment_tracker = models.ForeignKey(
        PaymentTracker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Webhook: {self.event_type} - {self.status}"
    
    class Meta:
        db_table = 'webhook_events'
        ordering = ['-created_at']


class PaymentTransaction(models.Model):
    """
    Tracks individual payment transactions per seller from checkout.session.completed
    Each seller in an order gets their own PaymentTransaction record
    """
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('held', 'On Hold'),
        ('processing', 'Processing'),
        ('released', 'Released to Seller'),
        ('disputed', 'Disputed'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]
    
    # Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payment_intent_id = models.CharField(max_length=255, db_index=True)
    stripe_checkout_session_id = models.CharField(max_length=255, db_index=True)
    
    # Relations
    order = models.ForeignKey(
        'marketplace.Order',
        on_delete=models.CASCADE,
        related_name='payment_transactions'
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payment_transactions_as_seller'
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payment_transactions_as_buyer'
    )
    
    # Payment Details
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    gross_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    platform_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    stripe_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    net_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Amount to be paid to seller after fees"
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Item Details
    item_count = models.PositiveIntegerField(default=1)
    item_names = models.TextField(help_text="Comma-separated list of item names")
    
    # Tracking
    purchase_date = models.DateTimeField(auto_now_add=True)
    payment_received_date = models.DateTimeField(null=True, blank=True)
    hold_release_date = models.DateTimeField(null=True, blank=True)
    
    # Notes and metadata
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['buyer', 'purchase_date']),
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['stripe_checkout_session_id']),
            models.Index(fields=['status', 'hold_release_date']),
        ]
    
    def save(self, *args, **kwargs):
        # Calculate net amount
        self.net_amount = self.gross_amount - self.platform_fee - self.stripe_fee
        super().save(*args, **kwargs)
    
    @property
    def is_held(self):
        return self.status == 'held'
    
    @property
    def can_be_released(self):
        return self.status == 'held' and self.hold_release_date and timezone.now() >= self.hold_release_date
    
    def release_payment(self, released_by=None, notes=""):
        """Release payment to seller (manual process only)"""
        if self.status == 'held':
            self.status = 'released'
            self.hold_release_date = timezone.now()
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=['status', 'hold_release_date', 'notes', 'updated_at'])
            return True
        return False
    
    def __str__(self):
        return f"Payment {str(self.id)[:8]} - {self.seller.username} - ${self.net_amount}"


class PaymentHold(models.Model):
    """
    Manages payment holding periods and release schedules
    """
    
    HOLD_REASON_CHOICES = [
        ('standard', 'Standard Hold Period'),
        ('new_seller', 'New Seller Verification'),
        ('high_value', 'High Value Transaction'),
        ('suspicious', 'Suspicious Activity'),
        ('dispute', 'Dispute Filed'),
        ('manual', 'Manual Hold'),
    ]
    
    HOLD_STATUS_CHOICES = [
        ('active', 'Active Hold'),
        ('released', 'Released'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Relations
    payment_transaction = models.OneToOneField(
        PaymentTransaction,
        on_delete=models.CASCADE,
        related_name='payment_hold'
    )
    
    # Hold Details
    reason = models.CharField(max_length=20, choices=HOLD_REASON_CHOICES, default='standard')
    status = models.CharField(max_length=20, choices=HOLD_STATUS_CHOICES, default='active')
    hold_days = models.PositiveIntegerField(default=30, help_text="Fixed 30-day hold period for all purchases")
    
    # Dates
    hold_start_date = models.DateTimeField(auto_now_add=True)
    planned_release_date = models.DateTimeField(null=True, blank=True)
    actual_release_date = models.DateTimeField(null=True, blank=True)
    
    # Notes
    hold_notes = models.TextField(blank=True)
    release_notes = models.TextField(blank=True)
    
    # Staff tracking
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_holds_created'
    )
    released_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_holds_released'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_holds'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'planned_release_date']),
            models.Index(fields=['payment_transaction', 'status']),
        ]
    
    def save(self, *args, **kwargs):
        # Calculate planned release date if not set
        if not self.planned_release_date:
            # If hold_start_date is not set yet (first save), use current time
            start_date = self.hold_start_date or timezone.now()
            self.planned_release_date = start_date + timezone.timedelta(days=self.hold_days)
        super().save(*args, **kwargs)
    
    @property
    def is_ready_for_release(self):
        return (self.status == 'active' and 
                self.planned_release_date and 
                timezone.now() >= self.planned_release_date)
    
    def release_hold(self, released_by=None, notes=""):
        """Release the payment hold"""
        if self.status == 'active':
            self.status = 'released'
            self.actual_release_date = timezone.now()
            self.released_by = released_by
            self.release_notes = notes
            self.save()
            
            # Update the payment transaction status
            self.payment_transaction.status = 'released'
            self.payment_transaction.hold_release_date = self.actual_release_date
            self.payment_transaction.save(update_fields=['status', 'hold_release_date', 'updated_at'])
            
            return True
        return False
    
    def __str__(self):
        return f"Hold for {self.payment_transaction} - {self.status} ({self.reason})"


class PaymentItem(models.Model):
    """
    Individual items within a payment transaction for detailed tracking
    """
    
    # Relations
    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.CASCADE,
        related_name='payment_items'
    )
    product = models.ForeignKey(
        'marketplace.Product',
        on_delete=models.CASCADE,
        related_name='payment_items'
    )
    order_item = models.ForeignKey(
        'marketplace.OrderItem',
        on_delete=models.CASCADE,
        related_name='payment_items'
    )
    
    # Item Details
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Product snapshot at time of payment
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_items'
        ordering = ['payment_transaction', 'product_name']
        indexes = [
            models.Index(fields=['payment_transaction', 'product']),
        ]
    
    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.quantity}x {self.product_name} - ${self.total_price}"