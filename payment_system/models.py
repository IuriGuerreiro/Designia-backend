from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
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