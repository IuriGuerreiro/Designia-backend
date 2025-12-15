"""
Exchange Rate Service

Provides programmatic interface for updating exchange rates.
This service wraps the management command functionality and provides
a clean API for automatic updates during server startup and scheduled updates.
"""

import logging
from typing import Dict, Optional

import requests
from django.utils import timezone


logger = logging.getLogger(__name__)


class ExchangeRateService:
    """
    Service for managing exchange rate updates programmatically.
    """

    # Free exchange rate API
    EXCHANGE_API_URL = "https://api.exchangerate-api.com/v4/latest/"

    @classmethod
    def update_exchange_rates(
        cls,
        base_currency: str = "USD",
        force_update: bool = False,
        cleanup_old: bool = True,
        source: str = "service",
        use_test_data: bool = False,
    ) -> Dict:
        """
        Update exchange rates from external API or test data.

        Args:
            base_currency (str): Base currency for exchange rates
            force_update (bool): Force update even if data is fresh
            cleanup_old (bool): Clean up old exchange rate data
            source (str): Source identifier for this update
            use_test_data (bool): Use test data instead of API

        Returns:
            dict: Result with success status, created count, and any errors
        """
        try:
            from ..models import ExchangeRate

            logger.info(f"[UPDATE] Starting exchange rate update (source: {source})")

            # Check if update is needed (unless forced)
            if not force_update and not use_test_data:
                if ExchangeRate.objects.is_data_fresh():
                    logger.info("[SKIP] Exchange rate data is fresh, skipping update")
                    return {
                        "success": True,
                        "created_count": 0,
                        "message": "Data is fresh, no update needed",
                        "skipped": True,
                    }

            # Get exchange rate data
            if use_test_data:
                rates_data = cls._get_test_data(base_currency)
                data_source = f"{source}_test_data"
            else:
                rates_data = cls._fetch_exchange_rates(base_currency)
                data_source = f"{source}_api"

            if not rates_data:
                error_msg = "Failed to fetch exchange rate data"
                logger.error(f"[ERROR] {error_msg}")
                return {"success": False, "created_count": 0, "error": error_msg}

            # Store rates in database
            created_count = ExchangeRate.bulk_create_rates(
                base_currency=base_currency, rates_dict=rates_data, source=data_source
            )

            logger.info(f"[SUCCESS] Created {created_count} exchange rates for {base_currency}")

            # Cleanup old data if requested
            if cleanup_old:
                try:
                    deleted_count = cls._cleanup_old_rates()
                    logger.info(f"[CLEANUP] Cleaned up {deleted_count} old exchange rate records")
                except Exception as cleanup_error:
                    logger.warning(f"[WARNING] Cleanup failed: {cleanup_error}")

            return {
                "success": True,
                "created_count": created_count,
                "base_currency": base_currency,
                "source": data_source,
                "message": f"Successfully updated {created_count} exchange rates",
            }

        except Exception as e:
            error_msg = f"Exchange rate update failed: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")
            return {"success": False, "created_count": 0, "error": error_msg}

    @classmethod
    def _fetch_exchange_rates(cls, base_currency: str) -> Optional[Dict]:
        """
        Fetch exchange rates from external API.

        Args:
            base_currency (str): Base currency code

        Returns:
            dict or None: Exchange rates data or None if failed
        """
        try:
            url = f"{cls.EXCHANGE_API_URL}{base_currency.upper()}"
            logger.debug(f"[FETCH] Fetching rates from: {url}")

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            if "rates" not in data:
                logger.error("[ERROR] Invalid response format from exchange rate API")
                return None

            rates = data["rates"]
            logger.info(f"[DATA] Fetched {len(rates)} exchange rates for {base_currency}")

            return rates

        except requests.RequestException as e:
            logger.error(f"[ERROR] Network error fetching exchange rates: {e}")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Error processing exchange rate data: {e}")
            return None

    @classmethod
    def _get_test_data(cls, base_currency: str) -> Dict:
        """
        Get test exchange rate data for development/testing.

        Args:
            base_currency (str): Base currency code

        Returns:
            dict: Test exchange rates
        """
        logger.info(f"[TEST] Using test exchange rate data for {base_currency}")

        # Comprehensive test rates for major currencies
        test_rates = {
            "USD": {
                "EUR": 0.85,
                "GBP": 0.73,
                "JPY": 110.0,
                "CAD": 1.25,
                "AUD": 1.35,
                "CHF": 0.92,
                "CNY": 6.45,
                "SEK": 8.5,
                "NOK": 8.8,
                "DKK": 6.3,
                "PLN": 3.9,
                "CZK": 21.5,
                "HUF": 295.0,
                "RUB": 75.0,
                "BRL": 5.2,
                "INR": 74.0,
                "KRW": 1180.0,
                "SGD": 1.35,
                "HKD": 7.8,
                "MXN": 20.1,
                "TRY": 8.5,
                "ZAR": 14.5,
                "THB": 31.5,
                "MYR": 4.1,
                "PHP": 49.5,
                "IDR": 14250.0,
                "VND": 22800.0,
                "ILS": 3.2,
                "CLP": 800.0,
                "TWD": 28.0,
            },
            "EUR": {
                "USD": 1.18,
                "GBP": 0.86,
                "JPY": 129.0,
                "CAD": 1.47,
                "AUD": 1.59,
                "CHF": 1.08,
                "CNY": 7.6,
                "SEK": 10.0,
                "NOK": 10.4,
                "DKK": 7.4,
                "PLN": 4.6,
                "CZK": 25.3,
                "HUF": 347.0,
                "RUB": 88.0,
            },
            "GBP": {
                "USD": 1.37,
                "EUR": 1.16,
                "JPY": 150.0,
                "CAD": 1.71,
                "AUD": 1.85,
                "CHF": 1.26,
                "CNY": 8.8,
                "SEK": 11.6,
                "NOK": 12.1,
                "DKK": 8.6,
            },
        }

        base_upper = base_currency.upper()
        if base_upper in test_rates:
            return test_rates[base_upper]
        else:
            # Convert USD rates to the requested base currency
            usd_rates = test_rates["USD"]
            if base_upper in usd_rates:
                base_to_usd = usd_rates[base_upper]
                converted_rates = {}
                for currency, rate in usd_rates.items():
                    if currency != base_upper:
                        converted_rates[currency] = rate / base_to_usd
                # Add USD rate
                converted_rates["USD"] = 1.0 / base_to_usd
                return converted_rates
            else:
                # Fallback to major currencies
                return {"USD": 1.0, "EUR": 0.85, "GBP": 0.73, "JPY": 110.0, "CAD": 1.25, "AUD": 1.35, "CHF": 0.92}

    @classmethod
    def _cleanup_old_rates(cls, keep_days: int = 7) -> int:
        """
        Clean up old exchange rate data.

        Args:
            keep_days (int): Number of days to keep

        Returns:
            int: Number of records deleted
        """
        try:
            from ..models import ExchangeRate

            cutoff_date = timezone.now() - timezone.timedelta(days=keep_days)
            deleted_count = ExchangeRate.objects.filter(created_at__lt=cutoff_date).delete()[0]

            return deleted_count

        except Exception as e:
            logger.error(f"[ERROR] Error cleaning up old rates: {e}")
            return 0

    @classmethod
    def get_exchange_rate_status(cls) -> Dict:
        """
        Get current status of exchange rate data.

        Returns:
            dict: Status information including freshness and last update
        """
        try:
            from ..models import ExchangeRate

            latest_rate = ExchangeRate.objects.order_by("-created_at").first()

            if latest_rate:
                age_hours = (timezone.now() - latest_rate.created_at).total_seconds() / 3600
                is_fresh = age_hours < 24

                # Count rates in latest batch
                total_rates = ExchangeRate.objects.filter(created_at=latest_rate.created_at).count()

                return {
                    "has_data": True,
                    "is_fresh": is_fresh,
                    "last_updated": latest_rate.created_at.isoformat(),
                    "age_hours": round(age_hours, 2),
                    "total_rates": total_rates,
                    "source": latest_rate.source,
                    "status": "fresh" if is_fresh else "stale",
                }
            else:
                return {
                    "has_data": False,
                    "is_fresh": False,
                    "last_updated": None,
                    "age_hours": None,
                    "total_rates": 0,
                    "source": None,
                    "status": "no_data",
                }

        except Exception as e:
            logger.error(f"[ERROR] Error getting exchange rate status: {e}")
            return {
                "has_data": False,
                "is_fresh": False,
                "last_updated": None,
                "age_hours": None,
                "total_rates": 0,
                "source": None,
                "status": "error",
                "error": str(e),
            }

    @classmethod
    def force_update_if_stale(cls, max_age_hours: int = 24) -> Dict:
        """
        Update exchange rates only if data is stale.

        Args:
            max_age_hours (int): Maximum age in hours before forcing update

        Returns:
            dict: Update result
        """
        status = cls.get_exchange_rate_status()

        if not status["has_data"] or (status["age_hours"] and status["age_hours"] > max_age_hours):
            logger.info(f"[STALE] Data is stale (age: {status.get('age_hours', 'unknown')}h), forcing update")
            return cls.update_exchange_rates(force_update=True, source="auto_stale_check")
        else:
            logger.info(f"[FRESH] Data is fresh (age: {status['age_hours']}h), no update needed")
            return {
                "success": True,
                "created_count": 0,
                "message": "Data is fresh, no update needed",
                "skipped": True,
                "status": status,
            }
