import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class StripeAccount(models.Model):
    """Represents a Stripe Connect account for marketplace sellers"""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="stripe_account")
    stripe_account_id = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=False)
    onboarding_completed = models.BooleanField(default=False)

    # Account details
    email = models.EmailField()
    country = models.CharField(max_length=2)  # ISO country code
    default_currency = models.CharField(max_length=3, default="USD")  # ISO currency code

    # Verification status
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    details_submitted = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stripe Account for {self.user.username}"

    class Meta:
        db_table = "payment_stripe_accounts"


class Payment(models.Model):
    """Main payment record for marketplace transactions"""

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
        ("disputed", "Disputed"),
    ]

    PAYMENT_TYPE_CHOICES = [
        ("order", "Order Payment"),
        ("refund", "Refund"),
        ("adjustment", "Adjustment"),
    ]

    # Unique identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_intent_id = models.CharField(max_length=255, unique=True)  # Stripe PaymentIntent ID

    # Relations
    order = models.ForeignKey("marketplace.Order", on_delete=models.CASCADE, related_name="payments")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payments_made")

    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Total payment amount
    currency = models.CharField(max_length=3, default="USD")
    application_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Marketplace fee

    # Status tracking
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending")
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default="order")

    # Hold system
    hold_until = models.DateTimeField()  # When funds are released to sellers
    is_held = models.BooleanField(default=True)
    hold_released_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    stripe_metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.hold_until:
            # Set hold period to 30 days from creation
            self.hold_until = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    def can_release_hold(self):
        """Check if payment hold can be released"""
        return self.is_held and self.status == "succeeded" and timezone.now() >= self.hold_until

    def release_hold(self):
        """Release payment hold and trigger seller payouts"""
        if self.can_release_hold():
            self.is_held = False
            self.hold_released_at = timezone.now()
            self.save()

            # Create seller payouts
            self.create_seller_payouts()
            return True
        return False

    def create_seller_payouts(self):
        """Create payout records for all sellers in the order"""
        for item in self.order.items.all():
            seller = item.product.seller
            seller_amount = item.total_price

            # Calculate application fee for this item
            item_fee = seller_amount * (self.application_fee / self.amount)
            net_amount = seller_amount - item_fee

            SellerPayout.objects.create(
                payment=self,
                seller=seller,
                stripe_account=seller.stripe_account,
                amount=net_amount,
                application_fee=item_fee,
                order_item=item,
            )

    def __str__(self):
        return f"Payment {self.payment_intent_id} - ${self.amount}"

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]


class SellerPayout(models.Model):
    """Individual payouts to sellers after payment hold release"""

    PAYOUT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    # Unique identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_transfer_id = models.CharField(max_length=255, null=True, blank=True)  # Stripe Transfer ID

    # Relations
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="seller_payouts")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payouts_received")
    stripe_account = models.ForeignKey(StripeAccount, on_delete=models.CASCADE)
    order_item = models.ForeignKey("marketplace.OrderItem", on_delete=models.CASCADE)

    # Payout details
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # Amount paid to seller
    application_fee = models.DecimalField(max_digits=10, decimal_places=2)  # Fee deducted
    currency = models.CharField(max_length=3, default="USD")

    # Status tracking
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default="pending")

    # Metadata
    stripe_metadata = models.JSONField(default=dict, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def process_payout(self):
        """Process the payout to seller's Stripe account"""
        if self.status != "pending":
            return False

        try:
            import stripe

            # Create transfer to seller's connected account
            transfer = stripe.Transfer.create(
                amount=int(self.amount * 100),  # Convert to cents
                currency=self.currency.lower(),
                destination=self.stripe_account.stripe_account_id,
                description=f"Payout for Order #{self.order_item.order.id}",
                metadata={
                    "payout_id": str(self.id),
                    "order_id": str(self.order_item.order.id),
                    "seller_id": str(self.seller.id),
                },
            )

            self.stripe_transfer_id = transfer.id
            self.status = "processing"
            self.save()

            return True

        except Exception as e:
            self.status = "failed"
            self.failure_reason = str(e)
            self.save()
            return False

    def __str__(self):
        return f"Payout ${self.amount} to {self.seller.username}"

    class Meta:
        db_table = "seller_payouts"
        ordering = ["-created_at"]


class PaymentTransaction(models.Model):
    """Detailed transaction log for all payment-related activities"""

    TRANSACTION_TYPE_CHOICES = [
        ("charge", "Charge"),
        ("refund", "Refund"),
        ("transfer", "Transfer"),
        ("payout", "Payout"),
        ("fee", "Application Fee"),
        ("dispute", "Dispute"),
        ("chargeback", "Chargeback"),
    ]

    # Unique identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_transaction_id = models.CharField(max_length=255, unique=True)

    # Relations
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="transactions")
    seller_payout = models.ForeignKey(SellerPayout, on_delete=models.CASCADE, null=True, blank=True)

    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    # Metadata
    description = models.CharField(max_length=255)
    stripe_metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField()

    def __str__(self):
        return f"{self.transaction_type.title()} ${self.amount}"

    class Meta:
        db_table = "payment_transactions"
        ordering = ["-processed_at"]


class RefundRequest(models.Model):
    """Refund requests with approval workflow"""

    REFUND_STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    REFUND_REASON_CHOICES = [
        ("defective", "Defective Item"),
        ("not_as_described", "Not as Described"),
        ("damaged_shipping", "Damaged in Shipping"),
        ("wrong_item", "Wrong Item Sent"),
        ("not_received", "Item Not Received"),
        ("buyer_remorse", "Buyer Remorse"),
        ("duplicate", "Duplicate Charge"),
        ("fraud", "Fraudulent Transaction"),
        ("other", "Other"),
    ]

    # Unique identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund_number = models.CharField(max_length=20, unique=True)

    # Relations
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refund_requests")
    order = models.ForeignKey("marketplace.Order", on_delete=models.CASCADE)
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refund_requests")
    approved_by = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="approved_refunds"
    )

    # Refund details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=50, choices=REFUND_REASON_CHOICES)
    description = models.TextField()

    # Status tracking
    status = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default="pending")

    # Stripe refund tracking
    stripe_refund_id = models.CharField(max_length=255, null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.refund_number:
            self.refund_number = f"REF{timezone.now().strftime('%Y%m%d')}{str(self.id)[-6:]}"
        super().save(*args, **kwargs)

    def approve_refund(self, approved_by_user):
        """Approve refund request"""
        if self.status == "pending":
            self.status = "approved"
            self.approved_by = approved_by_user
            self.approved_at = timezone.now()
            self.save()
            return True
        return False

    def process_refund(self):
        """Process the approved refund via Stripe"""
        if self.status != "approved":
            return False

        try:
            import stripe

            # Create refund in Stripe
            refund = stripe.Refund.create(
                payment_intent=self.payment.payment_intent_id,
                amount=int(self.amount * 100),  # Convert to cents
                reason="requested_by_customer",
                metadata={
                    "refund_request_id": str(self.id),
                    "order_id": str(self.order.id),
                    "reason": self.reason,
                },
            )

            self.stripe_refund_id = refund.id
            self.status = "processing"
            self.processed_at = timezone.now()
            self.save()

            return True

        except Exception:
            self.status = "failed"
            self.save()
            return False

    def __str__(self):
        return f"Refund Request {self.refund_number} - ${self.amount}"

    class Meta:
        db_table = "refund_requests"
        ordering = ["-created_at"]


class StripePaymentTracker(models.Model):
    """Enhanced Stripe payment tracking for security and audit purposes"""

    TRACKER_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("authorized", "Authorized"),
        ("captured", "Captured"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
        ("refunded", "Refunded"),
        ("partially_refunded", "Partially Refunded"),
        ("disputed", "Disputed"),
        ("requires_action", "Requires Action"),
    ]

    TRANSACTION_TYPE_CHOICES = [
        ("payment", "Payment"),
        ("refund", "Refund"),
        ("partial_refund", "Partial Refund"),
        ("dispute", "Dispute"),
        ("chargeback", "Chargeback"),
        ("reversal", "Reversal"),
        ("adjustment", "Adjustment"),
    ]

    # Unique identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Stripe identifiers - comprehensive tracking
    stripe_payment_intent_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_payment_method_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_charge_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_refund_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_transfer_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_payout_id = models.CharField(max_length=255, db_index=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, db_index=True, blank=True)

    # Relations - secure associations
    order = models.ForeignKey(
        "marketplace.Order",
        on_delete=models.PROTECT,  # PROTECT prevents accidental deletion
        related_name="stripe_trackers",
        db_index=True,
    )
    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="stripe_trackers", null=True, blank=True
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="stripe_payment_trackers", db_index=True)

    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, default="payment")
    status = models.CharField(max_length=20, choices=TRACKER_STATUS_CHOICES, default="pending")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    # Security and audit fields
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=255, blank=True)

    # Risk assessment
    risk_level = models.CharField(
        max_length=10,
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("blocked", "Blocked"),
        ],
        default="low",
    )
    fraud_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Status history
    previous_status = models.CharField(max_length=20, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="status_changes"
    )

    # Stripe metadata and webhook tracking
    stripe_metadata = models.JSONField(default=dict, blank=True)
    webhook_events = models.JSONField(default=list, blank=True)  # Track related webhook events

    # Additional tracking fields
    failure_reason = models.CharField(max_length=255, blank=True)
    dispute_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    # Timestamps - comprehensive audit trail
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    stripe_created_at = models.DateTimeField(null=True, blank=True)  # Stripe's creation timestamp
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Verification flags
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_payments"
    )

    def update_status(self, new_status, changed_by=None, notes=""):
        """Safely update status with audit trail"""
        if self.status != new_status:
            self.previous_status = self.status
            self.status = new_status
            self.status_changed_at = timezone.now()
            self.status_changed_by = changed_by
            if notes:
                self.notes = f"{self.notes}\n[{timezone.now()}] Status changed to {new_status}: {notes}".strip()
            self.save()

    def add_webhook_event(self, event_id, event_type):
        """Track webhook events related to this payment"""
        webhook_info = {"event_id": event_id, "event_type": event_type, "received_at": timezone.now().isoformat()}
        self.webhook_events.append(webhook_info)
        self.save(update_fields=["webhook_events", "updated_at"])

    def verify_payment(self, verified_by):
        """Mark payment as verified by admin/system"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_by = verified_by
        self.save()

    def get_stripe_dashboard_url(self):
        """Get Stripe dashboard URL for this payment"""
        if self.stripe_payment_intent_id:
            return f"https://dashboard.stripe.com/payments/{self.stripe_payment_intent_id}"
        elif self.stripe_charge_id:
            return f"https://dashboard.stripe.com/payments/{self.stripe_charge_id}"
        return None

    def is_suspicious(self):
        """Check if payment has suspicious characteristics"""
        return (
            self.risk_level in ["high", "blocked"]
            or (self.fraud_score and self.fraud_score > 75)
            or self.status in ["disputed", "failed"]
            or self.failure_reason in ["card_declined", "insufficient_funds", "fraudulent"]
        )

    def __str__(self):
        stripe_id = self.stripe_payment_intent_id or self.stripe_charge_id or "No Stripe ID"
        return f"Stripe Tracker: {stripe_id} - {self.transaction_type} ${self.amount} [{self.status}]"

    class Meta:
        db_table = "stripe_payment_trackers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["stripe_charge_id"]),
            models.Index(fields=["order", "transaction_type"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "risk_level"]),
            models.Index(fields=["created_at"]),
        ]
        unique_together = [
            ("stripe_payment_intent_id", "transaction_type"),
            ("stripe_charge_id", "transaction_type"),
        ]


class WebhookEvent(models.Model):
    """Log of Stripe webhook events for debugging and tracking"""

    EVENT_STATUS_CHOICES = [
        ("received", "Received"),
        ("processing", "Processing"),
        ("processed", "Processed"),
        ("failed", "Failed"),
        ("ignored", "Ignored"),
    ]

    # Event details
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)

    # Processing status
    status = models.CharField(max_length=20, choices=EVENT_STATUS_CHOICES, default="received")
    processing_attempts = models.IntegerField(default=0)
    last_processing_error = models.TextField(blank=True)

    # Event data
    event_data = models.JSONField()

    # Related payment tracker
    payment_tracker = models.ForeignKey(
        StripePaymentTracker, on_delete=models.SET_NULL, null=True, blank=True, related_name="webhook_events_log"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Webhook: {self.event_type} - {self.status}"

    class Meta:
        db_table = "webhook_events"
        ordering = ["-created_at"]
