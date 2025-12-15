import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from .payment_transaction import PaymentTransaction


User = get_user_model()


class Payout(models.Model):
    """
    Track Stripe payouts to seller bank accounts with all associated payment transfers.
    Each payout groups multiple completed payment transfers for a seller.
    """

    PAYOUT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_transit", "In Transit"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]

    PAYOUT_TYPE_CHOICES = [
        ("standard", "Standard Payout"),
        ("express", "Express Payout"),
        ("instant", "Instant Payout"),
    ]

    # Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payout_id = models.CharField(max_length=255, unique=True, db_index=True, help_text="Stripe payout ID")

    # Relations
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="payouts", help_text="Seller receiving the payout"
    )

    # Payout Details
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default="pending")
    payout_type = models.CharField(max_length=20, choices=PAYOUT_TYPE_CHOICES, default="standard")

    amount_cents = models.PositiveIntegerField(help_text="Total payout amount in cents")
    amount_decimal = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Total payout amount in decimal format"
    )
    currency = models.CharField(max_length=3, help_text="Payout currency")

    # Bank Account Details
    source_type = models.CharField(max_length=20, default="bank_account", help_text="Source type for payout")
    bank_account_last4 = models.CharField(max_length=4, blank=True, help_text="Last 4 digits of bank account")
    bank_name = models.CharField(max_length=100, blank=True, help_text="Bank name")

    # Transfer Summary
    transfer_count = models.PositiveIntegerField(default=0, help_text="Number of payment transfers included")
    total_gross_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Total gross amount from all transfers"
    )
    total_fees = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Total fees deducted"
    )

    # Stripe Details
    stripe_created_at = models.DateTimeField(null=True, blank=True, help_text="When payout was created in Stripe")
    arrival_date = models.DateTimeField(null=True, blank=True, help_text="Expected arrival date")

    # Failure Information
    failure_code = models.CharField(max_length=50, blank=True, help_text="Stripe failure code if failed")
    failure_message = models.TextField(blank=True, help_text="Failure message from Stripe")

    # Metadata
    description = models.TextField(blank=True, help_text="Description of the payout")
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional metadata")

    # Simple retry tracking
    retry_count = models.PositiveIntegerField(default=0, help_text="Number of retry attempts for failed payouts")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_payouts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["stripe_payout_id"]),
            models.Index(fields=["currency", "-created_at"]),
            models.Index(fields=["retry_count"]),
        ]

    def save(self, *args, **kwargs):
        """Calculate decimal amount from cents and update currency to uppercase."""
        if self.amount_cents:
            self.amount_decimal = Decimal(self.amount_cents) / 100
        if self.currency:
            self.currency = self.currency.upper()
        super().save(*args, **kwargs)

    @property
    def amount_formatted(self):
        """Get formatted amount string."""
        return f"{self.amount_decimal:.2f} {self.currency}"

    @property
    def is_completed(self):
        """Check if payout is completed (paid)."""
        return self.status == "paid"

    @property
    def is_failed(self):
        """Check if payout failed."""
        return self.status == "failed"

    @property
    def days_since_created(self):
        """Calculate days since payout was created."""
        return (timezone.now() - self.created_at).days

    def get_payment_transfers(self):
        """Get all payment transfers included in this payout."""
        return self.payout_items.select_related("payment_transfer")

    def calculate_totals(self):
        """Calculate and update payout totals from included transfers."""
        payout_items = self.payout_items.select_related("payment_transfer")

        total_gross = Decimal("0.00")
        total_fees = Decimal("0.00")
        transfer_count = 0

        for item in payout_items:
            transfer = item.payment_transfer
            total_gross += transfer.gross_amount
            total_fees += transfer.platform_fee + transfer.stripe_fee
            transfer_count += 1

        self.total_gross_amount = total_gross
        self.total_fees = total_fees
        self.transfer_count = transfer_count

        # Ensure amount_cents matches the sum of net amounts
        total_net = total_gross - total_fees
        self.amount_cents = int(total_net * 100)

        self.save(
            update_fields=[
                "total_gross_amount",
                "total_fees",
                "transfer_count",
                "amount_cents",
                "amount_decimal",
                "updated_at",
            ]
        )

    def update_status(self, new_status):
        """
        Simple status update without complex tracking.
        """
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

    def increment_retry_count(self):
        """Increment retry count for failed payouts."""
        self.retry_count += 1
        self.save(update_fields=["retry_count", "updated_at"])

    def __str__(self):
        return f"Payout {str(self.id)[:8]} - {self.seller.username} - {self.amount_formatted} ({self.status})"


class PayoutItem(models.Model):
    """
    Individual payment transfer included in a payout.
    Links PaymentTransactions to Payouts for detailed tracking.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations
    payout = models.ForeignKey(
        Payout, on_delete=models.CASCADE, related_name="payout_items", help_text="The payout this item belongs to"
    )
    payment_transfer = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.CASCADE,
        unique=False,  # Allow multiple items to reference the same transfer
        related_name="payout_items",
        help_text="The payment transfer included in the payout",
    )

    # Transfer Details (denormalized for performance)
    transfer_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Net amount of this transfer")
    transfer_currency = models.CharField(max_length=3, help_text="Currency of the transfer")
    transfer_date = models.DateTimeField(help_text="When the transfer was completed")

    # Order Information (denormalized)
    order_id = models.CharField(max_length=100, help_text="Order ID for reference")
    item_names = models.TextField(help_text="Items sold in this transfer")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_payout_items"
        ordering = ["-transfer_date"]
        indexes = [
            models.Index(fields=["payout", "-transfer_date"]),
            models.Index(fields=["payment_transfer"]),
            models.Index(fields=["order_id"]),
        ]
        # Removed unique_together constraint to allow payment transfers in multiple payouts
        # This enables audit trail of failed payout attempts

    def save(self, *args, **kwargs):
        """Auto-populate denormalized fields from payment transfer."""
        if self.payment_transfer and not self.transfer_amount:
            transfer = self.payment_transfer
            self.transfer_amount = transfer.net_amount
            self.transfer_currency = transfer.currency.upper()
            self.transfer_date = transfer.actual_release_date or transfer.updated_at
            self.order_id = str(transfer.order.id) if transfer.order else ""
            self.item_names = transfer.item_names

        super().save(*args, **kwargs)

    def __str__(self):
        return f"PayoutItem {self.order_id} - {self.transfer_amount} {self.transfer_currency}"
