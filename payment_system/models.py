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
        ('payment_intent', 'Payment Intent'),
        ('transfer', 'Transfer'),
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
    stripe_transfer_id = models.CharField(max_length=255, blank=True, db_index=True)
    
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
    
    # Payment Intent failure tracking (for payment_intent events)
    failure_code = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Stripe failure code for failed payment intents"
    )
    failure_reason = models.TextField(
        blank=True,
        help_text="Detailed failure reason for payment intent failures"
    )
    stripe_error_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Complete Stripe error data for payment intent failures"
    )
    
    # Additional payment intent tracking
    latest_charge_id = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Latest charge ID from payment intent"
    )
    payment_method_id = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Payment method ID used"
    )
    
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


class PaymentTransaction(models.Model):
    """
    Simplified payment tracking for sellers with integrated 30-day hold system
    Each seller in an order gets their own PaymentTransaction record
    """
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('held', 'On Hold'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('released', 'Released to Seller'),
        ('disputed', 'Disputed'),
        ('waiting_refund', 'Waiting for Refund'),
        ('refunded', 'Refunded'),
        ('failed_refund', 'Failed Refund'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    HOLD_REASON_CHOICES = [
        ('standard', 'Standard Hold Period'),
        ('new_seller', 'New Seller Verification'),
        ('high_value', 'High Value Transaction'),
        ('suspicious', 'Suspicious Activity'),
        ('dispute', 'Dispute Filed'),
        ('manual', 'Manual Hold'),
    ]
    
    # Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payment_intent_id = models.CharField(max_length=255, db_index=True)
    stripe_checkout_session_id = models.CharField(max_length=255, db_index=True)
    transfer_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="Stripe transfer ID when payment is transferred to seller")
    
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
    
    # Hold System - Integrated into PaymentTransaction
    hold_reason = models.CharField(max_length=20, choices=HOLD_REASON_CHOICES, default='standard')
    days_to_hold = models.PositiveIntegerField(default=30, help_text="Number of days to hold payment (default: 30)")
    hold_start_date = models.DateTimeField(null=True, blank=True, help_text="When hold period started")
    planned_release_date = models.DateTimeField(null=True, blank=True, help_text="Calculated release date")
    actual_release_date = models.DateTimeField(null=True, blank=True, help_text="When payment was actually released")
    hold_notes = models.TextField(blank=True)
    released_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='released_payment_transactions'
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
        db_table = 'payment_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['buyer', 'purchase_date']),
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['stripe_checkout_session_id']),
            models.Index(fields=['status', 'planned_release_date']),
            models.Index(fields=['hold_start_date']),
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
        return self.status == 'held'
    
    @property
    def is_processing(self):
        return self.status == 'processing'
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def can_transfer(self):
        """Check if this payment can be transferred (only 'held' payments can be transferred)"""
        return self.status == 'held'
    
    @property
    def can_be_released(self):
        """Check if payment can be released based on hold period and status"""
        return (self.status == 'held' and 
                self.planned_release_date and 
                timezone.now() >= self.planned_release_date)
    
    @property
    def days_remaining(self):
        """Calculate days remaining in hold period"""
        if not self.planned_release_date or self.status != 'held':
            return 0
        
        remaining = self.planned_release_date - timezone.now()
        return max(0, remaining.days)
    
    @property
    def hours_remaining(self):
        """Calculate hours remaining in hold period"""
        if not self.planned_release_date or self.status != 'held':
            return 0
            
        remaining = self.planned_release_date - timezone.now()
        if remaining.total_seconds() <= 0:
            return 0
        return remaining.seconds // 3600
    
    def start_hold(self, reason='standard', days=30, notes=""):
        """Start the hold period for this payment"""
        self.hold_reason = reason
        self.days_to_hold = days
        self.hold_start_date = timezone.now()
        self.planned_release_date = self.hold_start_date + timezone.timedelta(days=days)
        self.status = 'held'
        self.hold_notes = notes
        self.save(update_fields=[
            'hold_reason', 'days_to_hold', 'hold_start_date', 
            'planned_release_date', 'status', 'hold_notes', 'updated_at'
        ])
    
    def start_transfer(self, transfer_id, notes=""):
        """Mark payment as processing and store transfer ID"""
        if self.status == 'held':
            self.status = 'processing'
            self.transfer_id = transfer_id
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=[
                'status', 'transfer_id', 'notes', 'updated_at'
            ])
            return True
        return False
    
    def complete_transfer(self, notes=""):
        """Mark transfer as completed after webhook verification"""
        if self.status == 'processing':
            self.status = 'completed'
            self.actual_release_date = timezone.now()
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=[
                'status', 'actual_release_date', 'notes', 'updated_at'
            ])
            return True
        return False
    
    def fail_transfer(self, notes=""):
        """Mark transfer as failed and revert to held status"""
        if self.status == 'processing':
            self.status = 'held'
            self.transfer_id = None
            self.notes = f"{self.notes}\nTransfer failed: {notes}" if notes else f"{self.notes}\nTransfer failed"
            self.save(update_fields=[
                'status', 'transfer_id', 'notes', 'updated_at'
            ])
            return True
        return False
    
    def cancel_payment(self, cancellation_reason="", notes=""):
        """Mark payment as cancelled due to order cancellation"""
        self.status = 'cancelled'
        self.payment_failure_code = 'cancelled'
        self.payment_failure_reason = cancellation_reason or 'Payment cancelled due to order cancellation'
        if notes:
            self.notes = f"{self.notes}\n{notes}" if self.notes else notes
        self.save(update_fields=[
            'status', 'payment_failure_code', 'payment_failure_reason', 'notes', 'updated_at'
        ])
        return True

    def release_payment(self, released_by=None, notes=""):
        """Release payment to seller (legacy method - now redirects to complete_transfer)"""
        if self.status == 'held':
            self.status = 'released'
            self.actual_release_date = timezone.now()
            self.released_by = released_by
            self.notes = f"{self.notes}\n{notes}" if notes else self.notes
            self.save(update_fields=[
                'status', 'actual_release_date', 'released_by', 'notes', 'updated_at'
            ])
            return True
        elif self.status == 'processing':
            return self.complete_transfer(notes)
        return False
    
    def __str__(self):
        payout_status = " - Paid Out" if self.payed_out else ""
        return f"Payment {str(self.id)[:8]} - {self.seller.username} - ${self.net_amount} ({self.status}){payout_status}"


class ExchangeRateManager(models.Manager):
    """Custom manager for ExchangeRate model."""
    
    def get_latest_rates(self, base_currency='USD'):
        """
        Get the latest exchange rates for a base currency.
        
        Args:
            base_currency (str): Base currency code (default: USD)
            
        Returns:
            dict: Dictionary of currency codes to rates
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            base_upper = base_currency.upper()
            logger.debug(f"[MODEL_DEBUG] ExchangeRateManager.get_latest_rates called for {base_upper}")
            
            # Check if any rates exist for this base currency
            total_for_base = self.filter(base_currency=base_upper).count()
            logger.debug(f"[MODEL_DEBUG] Total rates in DB for {base_upper}: {total_for_base}")
            
            if total_for_base == 0:
                logger.debug(f"[MODEL_DEBUG] No rates found for {base_upper} - returning empty dict")
                return {}
            
            # Get the latest batch
            latest_batch = self.filter(
                base_currency=base_upper
            ).order_by('-created_at').first()
            
            if not latest_batch:
                logger.debug(f"[MODEL_DEBUG] No latest_batch found for {base_upper} - returning empty dict")
                return {}
            
            logger.debug(f"[MODEL_DEBUG] Latest batch for {base_upper}: created_at={latest_batch.created_at}")
            logger.debug(f"[MODEL_DEBUG] Latest batch rate example: {base_upper}->{latest_batch.target_currency}={latest_batch.rate}")
            
            # Get all rates from the latest date (not exact timestamp)
            # This fixes the issue where only ~20 rates were returned due to exact timestamp matching
            latest_date = latest_batch.created_at.date()
            rates_queryset = self.filter(
                base_currency=base_upper,
                created_at__date=latest_date
            ).order_by('-created_at').values('target_currency', 'rate')
            
            rates_list = list(rates_queryset)
            logger.debug(f"[MODEL_DEBUG] Found {len(rates_list)} rates in latest batch for {base_upper}")
            
            for rate_item in rates_list:
                logger.debug(f"[MODEL_DEBUG] Rate in batch: {base_upper}->{rate_item['target_currency']}={rate_item['rate']}")
            
            rates = {item['target_currency']: float(item['rate']) for item in rates_list}
            
            logger.debug(f"[MODEL_DEBUG] Returning rates dict with {len(rates)} entries: {list(rates.keys())}")
            return rates
            
        except Exception as e:
            logger.error(f"[MODEL_DEBUG] Exception in get_latest_rates: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[MODEL_DEBUG] Traceback: {traceback.format_exc()}")
            return {}
    
    def get_rate(self, base_currency, target_currency):
        """
        Get a specific exchange rate.
        
        Args:
            base_currency (str): Base currency code
            target_currency (str): Target currency code
            
        Returns:
            float or None: Exchange rate or None if not found
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            base_upper = base_currency.upper()
            target_upper = target_currency.upper()
            
            logger.debug(f"[MODEL_DEBUG] get_rate called for {base_upper} -> {target_upper}")
            
            # Check total rates for this currency pair
            total_rates = self.filter(
                base_currency=base_upper,
                target_currency=target_upper
            ).count()
            logger.debug(f"[MODEL_DEBUG] Total rates for {base_upper}->{target_upper}: {total_rates}")
            
            latest_rate = self.filter(
                base_currency=base_upper,
                target_currency=target_upper
            ).order_by('-created_at').first()
            
            if latest_rate:
                rate_value = float(latest_rate.rate)
                logger.debug(f"[MODEL_DEBUG] Found rate {base_upper}->{target_upper} = {rate_value} (created: {latest_rate.created_at})")
                return rate_value
            else:
                logger.debug(f"[MODEL_DEBUG] No rate found for {base_upper}->{target_upper}")
                return None
            
        except Exception as e:
            logger.error(f"[MODEL_DEBUG] Exception in get_rate: {type(e).__name__}: {e}")
            return None
    
    def get_rate_optimized(self, base_currency, target_currency):
        """
        Optimized method for single currency pair lookup with enhanced debugging.
        
        Args:
            base_currency (str): Base currency code  
            target_currency (str): Target currency code
            
        Returns:
            float or None: Exchange rate or None if not found
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            base_upper = base_currency.upper()
            target_upper = target_currency.upper()
            
            logger.debug(f"[MODEL_DEBUG] get_rate_optimized called for {base_upper} -> {target_upper}")
            
            # Direct query for latest rate of this specific pair
            latest_rate = self.filter(
                base_currency=base_upper,
                target_currency=target_upper
            ).order_by('-created_at').first()
            
            if latest_rate:
                rate_value = float(latest_rate.rate)
                age_hours = (timezone.now() - latest_rate.created_at).total_seconds() / 3600
                
                logger.debug(f"[MODEL_DEBUG] Rate found: {base_upper}->{target_upper} = {rate_value}")
                logger.debug(f"[MODEL_DEBUG] Rate age: {age_hours:.1f} hours (created: {latest_rate.created_at})")
                logger.debug(f"[MODEL_DEBUG] Rate source: {latest_rate.source}")
                
                return rate_value
            else:
                logger.debug(f"[MODEL_DEBUG] No rate found for {base_upper}->{target_upper}")
                
                # Check if base currency exists at all
                base_exists = self.filter(base_currency=base_upper).exists()
                logger.debug(f"[MODEL_DEBUG] Base currency {base_upper} exists in DB: {base_exists}")
                
                if base_exists:
                    # Show available target currencies for debugging
                    available_targets = self.filter(
                        base_currency=base_upper
                    ).values_list('target_currency', flat=True).distinct()[:10]
                    
                    logger.debug(f"[MODEL_DEBUG] Available targets for {base_upper}: {list(available_targets)}")
                
                return None
                
        except Exception as e:
            logger.error(f"[MODEL_DEBUG] Exception in get_rate_optimized: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[MODEL_DEBUG] Traceback: {traceback.format_exc()}")
            return None
    
    def is_data_fresh(self, max_age_hours=24):
        """
        Check if exchange rate data is fresh (within max_age_hours).
        
        Args:
            max_age_hours (int): Maximum age in hours (default: 24)
            
        Returns:
            bool: True if data is fresh, False otherwise
        """
        try:
            latest_rate = self.order_by('-created_at').first()
            
            if not latest_rate:
                return False
            
            age = timezone.now() - latest_rate.created_at
            return age.total_seconds() < (max_age_hours * 3600)
            
        except Exception:
            return False


class ExchangeRate(models.Model):
    """
    Model for storing currency exchange rates.
    
    This model stores exchange rates with timestamps to enable daily updates
    and historical tracking.
    """
    
    base_currency = models.CharField(
        max_length=3,
        help_text="Base currency code (e.g., USD, EUR)"
    )
    
    target_currency = models.CharField(
        max_length=3,
        help_text="Target currency code (e.g., EUR, GBP)"
    )
    
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        help_text="Exchange rate from base to target currency"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this rate was recorded"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this rate was last updated"
    )
    
    source = models.CharField(
        max_length=100,
        default='manual',
        help_text="Source of this exchange rate data"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this rate is currently active"
    )
    
    # Custom manager
    objects = ExchangeRateManager()
    
    class Meta:
        db_table = 'payment_exchange_rates'
        verbose_name = 'Exchange Rate'
        verbose_name_plural = 'Exchange Rates'
        
        # Ensure uniqueness per base/target/timestamp combination
        unique_together = ['base_currency', 'target_currency', 'created_at']
        
        # Index for performance
        indexes = [
            models.Index(fields=['base_currency', 'target_currency', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active']),
        ]
        
        # Default ordering
        ordering = ['-created_at', 'base_currency', 'target_currency']
    
    def __str__(self):
        return f"{self.base_currency}/{self.target_currency}: {self.rate} ({self.created_at.date()})"
    
    def save(self, *args, **kwargs):
        """Override save to ensure currency codes are uppercase."""
        self.base_currency = self.base_currency.upper()
        self.target_currency = self.target_currency.upper()
        super().save(*args, **kwargs)
    
    @property
    def age_hours(self):
        """Get the age of this rate in hours."""
        return (timezone.now() - self.created_at).total_seconds() / 3600
    
    @property
    def is_fresh(self):
        """Check if this rate is fresh (less than 24 hours old)."""
        return self.age_hours < 24
    
    @classmethod
    def bulk_create_rates(cls, base_currency, rates_dict, source='api'):
        """
        Bulk create exchange rates for a base currency.
        
        Args:
            base_currency (str): Base currency code
            rates_dict (dict): Dictionary of target_currency -> rate
            source (str): Source of the data
            
        Returns:
            int: Number of rates created
        """
        try:
            # Create timestamp for this batch
            batch_time = timezone.now()
            
            # Create rate objects
            rate_objects = []
            for target_currency, rate in rates_dict.items():
                if target_currency.upper() != base_currency.upper():  # Skip self-rates
                    rate_objects.append(
                        cls(
                            base_currency=base_currency.upper(),
                            target_currency=target_currency.upper(),
                            rate=Decimal(str(rate)),
                            created_at=batch_time,
                            source=source
                        )
                    )
            
            # Bulk create
            created_rates = cls.objects.bulk_create(rate_objects, ignore_conflicts=True)
            return len(created_rates)
            
        except Exception:
            return 0


class Payout(models.Model):
    """
    Track Stripe payouts to seller bank accounts with all associated payment transfers.
    Each payout groups multiple completed payment transfers for a seller.
    """
    
    PAYOUT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
    ]
    
    PAYOUT_TYPE_CHOICES = [
        ('standard', 'Standard Payout'),
        ('express', 'Express Payout'),
        ('instant', 'Instant Payout'),
    ]
    
    # Identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_payout_id = models.CharField(max_length=255, unique=True, db_index=True, help_text="Stripe payout ID")
    
    # Relations
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payouts',
        help_text="Seller receiving the payout"
    )
    
    # Payout Details
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default='pending')
    payout_type = models.CharField(max_length=20, choices=PAYOUT_TYPE_CHOICES, default='standard')
    
    amount_cents = models.PositiveIntegerField(help_text="Total payout amount in cents")
    amount_decimal = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Total payout amount in decimal format"
    )
    currency = models.CharField(max_length=3, help_text="Payout currency")
    
    # Bank Account Details
    source_type = models.CharField(max_length=20, default='bank_account', help_text="Source type for payout")
    bank_account_last4 = models.CharField(max_length=4, blank=True, help_text="Last 4 digits of bank account")
    bank_name = models.CharField(max_length=100, blank=True, help_text="Bank name")
    
    # Transfer Summary
    transfer_count = models.PositiveIntegerField(default=0, help_text="Number of payment transfers included")
    total_gross_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total gross amount from all transfers"
    )
    total_fees = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total fees deducted"
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
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_payouts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['stripe_payout_id']),
            models.Index(fields=['currency', '-created_at']),
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
        return self.status == 'paid'
    
    @property
    def is_failed(self):
        """Check if payout failed."""
        return self.status == 'failed'
    
    @property
    def days_since_created(self):
        """Calculate days since payout was created."""
        return (timezone.now() - self.created_at).days
    
    def get_payment_transfers(self):
        """Get all payment transfers included in this payout."""
        return self.payout_items.select_related('payment_transfer')
    
    def calculate_totals(self):
        """Calculate and update payout totals from included transfers."""
        payout_items = self.payout_items.select_related('payment_transfer')
        
        total_gross = Decimal('0.00')
        total_fees = Decimal('0.00')
        transfer_count = 0
        
        for item in payout_items:
            transfer = item.payment_transfer
            total_gross += transfer.gross_amount
            total_fees += (transfer.platform_fee + transfer.stripe_fee)
            transfer_count += 1
        
        self.total_gross_amount = total_gross
        self.total_fees = total_fees
        self.transfer_count = transfer_count
        
        # Ensure amount_cents matches the sum of net amounts
        total_net = total_gross - total_fees
        self.amount_cents = int(total_net * 100)
        
        self.save(update_fields=[
            'total_gross_amount', 'total_fees', 'transfer_count', 
            'amount_cents', 'amount_decimal', 'updated_at'
        ])
    
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
        Payout,
        on_delete=models.CASCADE,
        related_name='payout_items',
        help_text="The payout this item belongs to"
    )
    payment_transfer = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.CASCADE,
        unique=False,  # Allow multiple items to reference the same transfer
        related_name='payout_items',
        help_text="The payment transfer included in the payout"
    )
    
    # Transfer Details (denormalized for performance)
    transfer_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Net amount of this transfer"
    )
    transfer_currency = models.CharField(max_length=3, help_text="Currency of the transfer")
    transfer_date = models.DateTimeField(help_text="When the transfer was completed")
    
    # Order Information (denormalized)
    order_id = models.CharField(max_length=100, help_text="Order ID for reference")
    item_names = models.TextField(help_text="Items sold in this transfer")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_payout_items'
        ordering = ['-transfer_date']
        indexes = [
            models.Index(fields=['payout', '-transfer_date']),
            models.Index(fields=['payment_transfer']),
            models.Index(fields=['order_id']),
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
            self.order_id = str(transfer.order.id) if transfer.order else ''
            self.item_names = transfer.item_names
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"PayoutItem {self.order_id} - {self.transfer_amount} {self.transfer_currency}"

