import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


User = get_user_model()


class PaymentTransaction(models.Model):
    """
    Simplified payment tracking for sellers with integrated 30-day hold system
    Each seller in an order gets their own PaymentTransaction record
    """

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("held", "On Hold"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("released", "Released to Seller"),
        ("disputed", "Disputed"),
        ("waiting_refund", "Waiting for Refund"),
        ("refunded", "Refunded"),
        ("failed_refund", "Failed Refund"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    HOLD_REASON_CHOICES = [
        ("standard", "Standard Hold Period"),
        ("new_seller", "New Seller Verification"),
        ("high_value", "High Value Transaction"),
        ("suspicious", "Suspicious Activity"),
        ("dispute", "Dispute Filed"),
        ("manual", "Manual Hold"),
    ]

    # Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payment_intent_id = models.CharField(max_length=255, db_index=True)
    stripe_checkout_session_id = models.CharField(max_length=255, db_index=True)
    transfer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Stripe transfer ID when payment is transferred to seller",
    )

    # Relations
    order = models.ForeignKey("marketplace.Order", on_delete=models.CASCADE, related_name="payment_transactions")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_transactions_as_seller")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_transactions_as_buyer")

    # Payment Details
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending")
    gross_amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    stripe_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Amount to be paid to seller after fees"
    )
    currency = models.CharField(max_length=3, default="USD")

    # Item Details
    item_count = models.PositiveIntegerField(default=1)
    item_names = models.TextField(help_text="Comma-separated list of item names")

    # Hold System - Integrated into PaymentTransaction
    hold_reason = models.CharField(max_length=20, choices=HOLD_REASON_CHOICES, default="standard")
    days_to_hold = models.PositiveIntegerField(default=30, help_text="Number of days to hold payment (default: 30)")
    hold_start_date = models.DateTimeField(null=True, blank=True, help_text="When hold period started")
    planned_release_date = models.DateTimeField(null=True, blank=True, help_text="Calculated release date")
    actual_release_date = models.DateTimeField(null=True, blank=True, help_text="When payment was actually released")
    hold_notes = models.TextField(blank=True)
    released_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="released_payment_transactions"
    )

    # Tracking
    purchase_date = models.DateTimeField(auto_now_add=True)
    payment_received_date = models.DateTimeField(null=True, blank=True)
    payed_out = models.BooleanField(default=False, help_text="True if this transfer has been included in a payout")

    # Notes and metadata
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller", "status"]),
            models.Index(fields=["buyer", "purchase_date"]),
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["stripe_checkout_session_id"]),
            models.Index(fields=["status", "planned_release_date"]),
            models.Index(fields=["hold_start_date"]),
        ]

    def save(self, *args, **kwargs):
        # Calculate net amount
        self.net_amount = self.gross_amount - self.platform_fee - self.stripe_fee

        # Auto-calculate planned release date if hold_start_date is set but planned_release_date is not
        if self.hold_start_date and not self.planned_release_date:
            self.planned_release_date = self.hold_start_date + timezone.timedelta(days=self.days_to_hold)

        super().save(*args, **kwargs)

    @property
    def is_held(self):
        return self.status == "held"

    @property
    def is_processing(self):
        return self.status == "processing"

    @property
    def is_completed(self):
        return self.status == "completed"

    @property
    def can_transfer(self):
        """Check if this payment can be transferred (only 'held' payments can be transferred)"""
        return self.status == "held"

    @property
    def can_be_released(self):
        """Check if payment can be released based on hold period and status"""
        return self.status == "held" and self.planned_release_date and timezone.now() >= self.planned_release_date

    @property
    def days_remaining(self):
        """Calculate days remaining in hold period"""
        if not self.planned_release_date or self.status != "held":
            return 0

        remaining = self.planned_release_date - timezone.now()
        return max(0, remaining.days)

    @property
    def hours_remaining(self):
        """Calculate hours remaining in hold period"""
        if not self.planned_release_date or self.status != "held":
            return 0

        remaining = self.planned_release_date - timezone.now()
        if remaining.total_seconds() <= 0:
            return 0
        return remaining.seconds // 3600

    def start_hold(self, reason="standard", days=30, notes=""):
        """Start the hold period for this payment"""
        self.hold_reason = reason
        self.days_to_hold = days
        self.hold_start_date = timezone.now()
        self.planned_release_date = self.hold_start_date + timezone.timedelta(days=days)
        self.status = "held"
        self.hold_notes = notes
        self.save(
            update_fields=[
                "hold_reason",
                "days_to_hold",
                "hold_start_date",
                "planned_release_date",
                "status",
                "hold_notes",
                "updated_at",
            ]
        )

    def start_transfer(self, transfer_id, notes=""):
        """Mark payment as processing and store transfer ID"""
        if self.status == "held":
            self.status = "processing"
            self.transfer_id = transfer_id
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=["status", "transfer_id", "notes", "updated_at"])
            return True
        return False

    def complete_transfer(self, notes=""):
        """Mark transfer as completed after webhook verification"""
        if self.status == "processing":
            self.status = "completed"
            self.actual_release_date = timezone.now()
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=["status", "actual_release_date", "notes", "updated_at"])
            return True
        return False

    def fail_transfer(self, notes=""):
        """Mark transfer as failed and revert to held status"""
        if self.status == "processing":
            self.status = "held"
            self.transfer_id = None
            self.notes = f"{self.notes}\nTransfer failed: {notes}" if notes else f"{self.notes}\nTransfer failed"
            self.save(update_fields=["status", "transfer_id", "notes", "updated_at"])
            return True
        return False

    def cancel_payment(self, cancellation_reason="", notes=""):
        """Mark payment as cancelled due to order cancellation"""
        self.status = "cancelled"
        self.payment_failure_code = "cancelled"
        self.payment_failure_reason = cancellation_reason or "Payment cancelled due to order cancellation"
        if notes:
            self.notes = f"{self.notes}\n{notes}" if self.notes else notes
        self.save(update_fields=["status", "payment_failure_code", "payment_failure_reason", "notes", "updated_at"])
        return True

    def release_payment(self, released_by=None, notes=""):
        """Release payment to seller (legacy method - now redirects to complete_transfer)"""
        if self.status == "held":
            self.status = "released"
            self.actual_release_date = timezone.now()
            self.released_by = released_by
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=["status", "actual_release_date", "released_by", "notes", "updated_at"])
            return True
        elif self.status == "processing":
            return self.complete_transfer(notes)
        return False

    def __str__(self):
        payout_status = " - Paid Out" if self.payed_out else ""
        return (
            f"Payment {str(self.id)[:8]} - {self.seller.username} - ${self.net_amount} ({self.status}){payout_status}"
        )
