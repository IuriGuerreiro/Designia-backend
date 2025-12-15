import uuid

from django.contrib.auth import get_user_model
from django.db import models


User = get_user_model()


class PaymentTracker(models.Model):
    """Simple payment tracking table to associate Stripe payment IDs with orders"""

    TRANSACTION_TYPE_CHOICES = [
        ("payment", "Payment"),
        ("refund", "Refund"),
        ("partial_refund", "Partial Refund"),
        ("payment_intent", "Payment Intent"),
        ("transfer", "Transfer"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
        ("refunded", "Refunded"),
        ("partially_refunded", "Partially Refunded"),
        ("payout_processing", "Payout Processing"),
        ("payout_success", "Payout Success"),
        ("payout_failed", "Payout Failed"),
    ]

    # Basic identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_refund_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_transfer_id = models.CharField(max_length=255, blank=True, db_index=True)

    # Relations
    order = models.ForeignKey(
        "marketplace.Order", on_delete=models.CASCADE, related_name="payment_trackers", db_index=True
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_trackers", db_index=True)

    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, default="payment")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    # Optional tracking fields
    notes = models.TextField(blank=True)

    # Payment Intent failure tracking (for payment_intent events)
    failure_code = models.CharField(
        max_length=50, blank=True, help_text="Stripe failure code for failed payment intents"
    )
    failure_reason = models.TextField(blank=True, help_text="Detailed failure reason for payment intent failures")
    stripe_error_data = models.JSONField(
        null=True, blank=True, help_text="Complete Stripe error data for payment intent failures"
    )

    # Additional payment intent tracking
    latest_charge_id = models.CharField(max_length=255, blank=True, help_text="Latest charge ID from payment intent")
    payment_method_id = models.CharField(max_length=255, blank=True, help_text="Payment method ID used")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        stripe_id = self.stripe_payment_intent_id or self.stripe_refund_id or "No Stripe ID"
        return f"{self.transaction_type.title()}: {stripe_id} - ${self.amount} [{self.status}]"

    class Meta:
        db_table = "payment_trackers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["stripe_refund_id"]),
            models.Index(fields=["order", "transaction_type"]),
            models.Index(fields=["user", "status"]),
        ]
