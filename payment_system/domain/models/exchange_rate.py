from decimal import Decimal

from django.db import models
from django.utils import timezone


class ExchangeRateManager(models.Manager):
    """Custom manager for ExchangeRate model."""

    def get_latest_rates(self, base_currency="USD"):
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
            latest_batch = self.filter(base_currency=base_upper).order_by("-created_at").first()

            if not latest_batch:
                logger.debug(f"[MODEL_DEBUG] No latest_batch found for {base_upper} - returning empty dict")
                return {}

            logger.debug(f"[MODEL_DEBUG] Latest batch for {base_upper}: created_at={latest_batch.created_at}")
            logger.debug(
                f"[MODEL_DEBUG] Latest batch rate example: {base_upper}->{latest_batch.target_currency}={latest_batch.rate}"
            )

            # Get all rates from the latest date (not exact timestamp)
            # This fixes the issue where only ~20 rates were returned due to exact timestamp matching
            latest_date = latest_batch.created_at.date()
            rates_queryset = (
                self.filter(base_currency=base_upper, created_at__date=latest_date)
                .order_by("-created_at")
                .values("target_currency", "rate")
            )

            rates_list = list(rates_queryset)
            logger.debug(f"[MODEL_DEBUG] Found {len(rates_list)} rates in latest batch for {base_upper}")

            for rate_item in rates_list:
                logger.debug(
                    f"[MODEL_DEBUG] Rate in batch: {base_upper}->{rate_item['target_currency']}={rate_item['rate']}"
                )

            rates = {item["target_currency"]: float(item["rate"]) for item in rates_list}

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
            total_rates = self.filter(base_currency=base_upper, target_currency=target_upper).count()
            logger.debug(f"[MODEL_DEBUG] Total rates for {base_upper}->{target_upper}: {total_rates}")

            latest_rate = (
                self.filter(base_currency=base_upper, target_currency=target_upper).order_by("-created_at").first()
            )

            if latest_rate:
                rate_value = float(latest_rate.rate)
                logger.debug(
                    f"[MODEL_DEBUG] Found rate {base_upper}->{target_upper} = {rate_value} (created: {latest_rate.created_at})"
                )
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
            latest_rate = (
                self.filter(base_currency=base_upper, target_currency=target_upper).order_by("-created_at").first()
            )

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
                    available_targets = (
                        self.filter(base_currency=base_upper).values_list("target_currency", flat=True).distinct()[:10]
                    )

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
            latest_rate = self.order_by("-created_at").first()

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

    base_currency = models.CharField(max_length=3, help_text="Base currency code (e.g., USD, EUR)")

    target_currency = models.CharField(max_length=3, help_text="Target currency code (e.g., EUR, GBP)")

    rate = models.DecimalField(max_digits=12, decimal_places=6, help_text="Exchange rate from base to target currency")

    created_at = models.DateTimeField(auto_now_add=True, help_text="When this rate was recorded")

    updated_at = models.DateTimeField(auto_now=True, help_text="When this rate was last updated")

    source = models.CharField(max_length=100, default="manual", help_text="Source of this exchange rate data")

    is_active = models.BooleanField(default=True, help_text="Whether this rate is currently active")

    # Custom manager
    objects = ExchangeRateManager()

    class Meta:
        db_table = "payment_exchange_rates"
        verbose_name = "Exchange Rate"
        verbose_name_plural = "Exchange Rates"

        # Ensure uniqueness per base/target/timestamp combination
        unique_together = ["base_currency", "target_currency", "created_at"]

        # Index for performance
        indexes = [
            models.Index(fields=["base_currency", "target_currency", "-created_at"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_active"]),
        ]

        # Default ordering
        ordering = ["-created_at", "base_currency", "target_currency"]

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
    def bulk_create_rates(cls, base_currency, rates_dict, source="api"):
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
                            source=source,
                        )
                    )

            # Bulk create
            created_rates = cls.objects.bulk_create(rate_objects, ignore_conflicts=True)
            return len(created_rates)

        except Exception:
            return 0
