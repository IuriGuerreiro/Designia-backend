"""
Currency handling system for Stripe transfers with balance checking and currency conversion.
Now uses local database storage for exchange rates instead of external APIs.
Refactored to use PaymentProvider interface.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Tuple

from django.utils import timezone

from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider


logger = logging.getLogger(__name__)


class CurrencyHandler:
    """
    Handles currency conversion, balance checking, and optimal currency selection for transfers.
    Now uses local database storage for exchange rates with daily updates.
    """

    # Major currencies in order of preference
    PREFERRED_CURRENCIES = ["usd", "eur", "gbp", "cad", "aud", "jpy", "chf", "sek", "nok", "dkk"]

    _provider = None

    @classmethod
    def get_provider(cls):
        if cls._provider is None:
            cls._provider = StripePaymentProvider()
        return cls._provider

    @staticmethod
    def get_stripe_balance() -> Dict:
        """
        Get current Stripe account balance with all available currencies.

        Returns:
            dict: Stripe balance object with available, pending, and reserved amounts
        """
        try:
            logger.debug("[STRIPE_DEBUG] Retrieving Stripe account balance...")
            provider = CurrencyHandler.get_provider()
            balance = provider.retrieve_balance()

            logger.debug("[STRIPE_DEBUG] Stripe balance retrieved successfully")
            logger.debug(f"[STRIPE_DEBUG] Available currencies: {len(balance.available)}")
            logger.debug(f"[STRIPE_DEBUG] Pending currencies: {len(balance.pending)}")

            # Debug: Log all available balances
            for i, currency_balance in enumerate(balance.available):
                currency = currency_balance["currency"]
                amount = currency_balance["amount"]
                amount_decimal = amount / 100
                logger.debug(f"[STRIPE_DEBUG] Available[{i}]: {amount} {currency} ({amount_decimal:.2f})")

            # Debug: Log all pending balances
            for i, currency_balance in enumerate(balance.pending):
                currency = currency_balance["currency"]
                amount = currency_balance["amount"]
                amount_decimal = amount / 100
                logger.debug(f"[STRIPE_DEBUG] Pending[{i}]: {amount} {currency} ({amount_decimal:.2f})")

            # Debug: Check if there are any reserved amounts
            if hasattr(balance, "reserved") and balance.reserved:
                logger.debug(f"[STRIPE_DEBUG] Reserved currencies: {len(balance.reserved)}")
                for i, currency_balance in enumerate(balance.reserved):
                    currency = currency_balance["currency"]
                    amount = currency_balance["amount"]
                    amount_decimal = amount / 100
                    logger.debug(f"[STRIPE_DEBUG] Reserved[{i}]: {amount} {currency} ({amount_decimal:.2f})")

            logger.info(f"Retrieved Stripe balance: {len(balance.available)} currencies available")
            return balance
        except Exception as e:
            logger.error(f"[STRIPE_DEBUG] API error: {type(e).__name__}: {e}")
            logger.error(f"Failed to retrieve Stripe balance: {e}")
            raise

    @staticmethod
    def get_available_currencies_with_balance() -> List[Dict]:
        """
        Get list of currencies with available balance, sorted by amount (highest first).

        Returns:
            list: List of dicts with currency, amount, and amount_formatted
        """
        try:
            logger.debug("[BALANCE_DEBUG] Getting available currencies with balance...")
            balance = CurrencyHandler.get_stripe_balance()

            available_currencies = []
            total_available = len(balance.available)
            currencies_with_balance = 0

            logger.debug(f"[BALANCE_DEBUG] Processing {total_available} available currency entries...")

            for i, currency_balance in enumerate(balance.available):
                currency = currency_balance["currency"].upper()
                amount_cents = currency_balance["amount"]
                amount_decimal = Decimal(amount_cents) / 100

                logger.debug(
                    f"[BALANCE_DEBUG] Processing currency[{i}]: {currency} = {amount_cents} cents ({amount_decimal:.2f})"
                )

                if currency_balance["amount"] > 0:
                    currencies_with_balance += 1

                    currency_info = {
                        "currency": currency,
                        "currency_code": currency_balance["currency"].lower(),
                        "amount_cents": amount_cents,
                        "amount_decimal": amount_decimal,
                        "amount_formatted": f"{amount_decimal:.2f} {currency}",
                        "source_types": currency_balance.get("source_types", {}),
                    }

                    available_currencies.append(currency_info)
                    logger.debug(f"[BALANCE_DEBUG] Added currency: {currency_info}")
                else:
                    logger.debug(f"[BALANCE_DEBUG] Skipping {currency} - zero balance")

            logger.debug(
                f"[BALANCE_DEBUG] Found {currencies_with_balance} currencies with positive balance out of {total_available} total"
            )

            # Sort by amount (highest first), then by preference
            logger.debug("[BALANCE_DEBUG] Sorting currencies by amount and preference...")

            def sort_key(x):
                amount_key = x["amount_cents"]
                preference_key = (
                    -CurrencyHandler.PREFERRED_CURRENCIES.index(x["currency_code"])
                    if x["currency_code"] in CurrencyHandler.PREFERRED_CURRENCIES
                    else 999
                )
                logger.debug(
                    f"[BALANCE_DEBUG] Sort key for {x['currency']}: amount={amount_key}, preference={preference_key}"
                )
                return (amount_key, preference_key)

            available_currencies.sort(key=sort_key, reverse=True)

            logger.debug("[BALANCE_DEBUG] Final sorted order:")
            for i, curr in enumerate(available_currencies):
                logger.debug(f"[BALANCE_DEBUG] {i + 1}. {curr['currency']}: {curr['amount_formatted']}")

            return available_currencies

        except Exception as e:
            logger.error(
                f"[BALANCE_DEBUG] Exception in get_available_currencies_with_balance: {type(e).__name__}: {e}"
            )
            logger.error(f"Error getting available currencies: {e}")
            return []

    @staticmethod
    def get_exchange_rates(base_currency: str = "USD") -> Dict[str, float]:
        """
        Get current exchange rates from database for base currency to other currencies.

        Args:
            base_currency (str): Base currency code (e.g., 'USD', 'EUR')

        Returns:
            dict: Exchange rates with currency codes as keys
        """
        try:
            from .models import ExchangeRate

            logger.debug(f"[DB_DEBUG] Attempting to retrieve exchange rates for {base_currency}")

            # Debug: Check total exchange rates in database
            total_rates = ExchangeRate.objects.count()
            logger.debug(f"[DB_DEBUG] Total exchange rates in database: {total_rates}")

            # Debug: Check rates for specific base currency
            base_currency_upper = base_currency.upper()
            base_rates_count = ExchangeRate.objects.filter(base_currency=base_currency_upper).count()
            logger.debug(f"[DB_DEBUG] Exchange rates for {base_currency_upper}: {base_rates_count}")

            if base_rates_count > 0:
                # Debug: Show recent rates for this base currency
                recent_rates = ExchangeRate.objects.filter(base_currency=base_currency_upper).order_by("-created_at")[
                    :5
                ]

                for rate in recent_rates:
                    logger.debug(
                        f"[DB_DEBUG] Rate found: {rate.base_currency}->{rate.target_currency}={rate.rate} (created: {rate.created_at})"
                    )

            # Get rates from database
            rates = ExchangeRate.objects.get_latest_rates(base_currency_upper)

            logger.debug(
                f"[DB_DEBUG] get_latest_rates returned: {type(rates)} with {len(rates) if rates else 0} items"
            )
            if rates:
                logger.debug(f"[DB_DEBUG] Available rates: {list(rates.keys())}")
                for curr, rate in rates.items():
                    logger.debug(f"[DB_DEBUG] Rate detail: {base_currency_upper}->{curr}={rate}")

            if rates:
                logger.info(f"Retrieved {len(rates)} exchange rates for {base_currency} from database")
                return rates
            else:
                logger.error(f"[DB_DEBUG] No exchange rates found in database for {base_currency}")
                logger.error(
                    f"[DB_DEBUG] Total rates in DB: {total_rates}, Rates for {base_currency_upper}: {base_rates_count}"
                )
                raise ValueError(f"No exchange rates available for {base_currency}. Please update exchange rate data.")

        except ValueError:
            # Re-raise ValueError (our custom errors)
            raise
        except Exception as e:
            logger.error(f"[DB_DEBUG] Exception in get_exchange_rates: {type(e).__name__}: {e}")
            logger.error(f"Error retrieving exchange rates from database: {e}")
            raise ValueError(f"Failed to retrieve exchange rates for {base_currency}: {str(e)}") from e

    @staticmethod
    def check_exchange_rate_freshness() -> Dict:
        """
        Check if exchange rate data is fresh and provide status information.

        Returns:
            dict: Status information about exchange rate data freshness
        """
        try:
            from .models import ExchangeRate

            is_fresh = ExchangeRate.objects.is_data_fresh()
            latest_rate = ExchangeRate.objects.order_by("-created_at").first()

            if latest_rate:
                age_hours = (timezone.now() - latest_rate.created_at).total_seconds() / 3600
                total_rates = ExchangeRate.objects.filter(created_at=latest_rate.created_at).count()

                return {
                    "is_fresh": is_fresh,
                    "last_updated": latest_rate.created_at.isoformat(),
                    "age_hours": round(age_hours, 2),
                    "total_rates": total_rates,
                    "source": latest_rate.source,
                    "status": "fresh" if is_fresh else "stale",
                    "needs_update": not is_fresh,
                }
            else:
                return {
                    "is_fresh": False,
                    "last_updated": None,
                    "age_hours": None,
                    "total_rates": 0,
                    "source": None,
                    "status": "no_data",
                    "needs_update": True,
                }

        except Exception as e:
            logger.error(f"Error checking exchange rate freshness: {e}")
            return {
                "is_fresh": False,
                "last_updated": None,
                "age_hours": None,
                "total_rates": 0,
                "source": None,
                "status": "error",
                "needs_update": True,
                "error": str(e),
            }

    @staticmethod
    def convert_currency(amount: Decimal, from_currency: str, to_currency: str) -> Tuple[Decimal, float]:
        """
        Convert amount from one currency to another using optimized targeted lookup.

        Args:
            amount (Decimal): Amount to convert
            from_currency (str): Source currency code
            to_currency (str): Target currency code

        Returns:
            tuple: (converted_amount, exchange_rate) or (original_amount, 1.0) if conversion fails
        """
        if from_currency.lower() == to_currency.lower():
            return amount, 1.0

        try:
            from .models import ExchangeRate

            logger.debug(f"[CONVERT_DEBUG] Converting {amount} {from_currency} to {to_currency}")

            # Use optimized targeted lookup instead of fetching all rates
            target_rate = ExchangeRate.objects.get_rate_optimized(from_currency.upper(), to_currency.upper())

            if target_rate is None:
                logger.error(
                    f"[CONVERT_DEBUG] No exchange rate found for {from_currency} -> {to_currency} in database"
                )
                raise ValueError(
                    f"Exchange rate not available for {from_currency} to {to_currency}. Please update exchange rate data."
                )

            converted_amount = amount * Decimal(str(target_rate))

            logger.info(
                f"Converted {amount} {from_currency} to {converted_amount:.2f} {to_currency} (rate: {target_rate})"
            )
            logger.debug("[CONVERT_DEBUG] Conversion successful using targeted lookup")

            return converted_amount, target_rate

        except ValueError:
            # Re-raise ValueError (our custom errors)
            raise
        except Exception as e:
            logger.error(f"[CONVERT_DEBUG] Currency conversion error: {type(e).__name__}: {e}")
            logger.error(f"Currency conversion error: {e}")
            raise ValueError(f"Currency conversion failed: {str(e)}") from e

    @staticmethod
    def check_currency_balance(currency: str, required_amount_cents: int) -> Dict:
        """
        Check if there's sufficient balance in the specified currency.

        Args:
            currency (str): Currency code to check
            required_amount_cents (int): Required amount in cents

        Returns:
            dict: Balance check result with availability and balance info
        """
        try:
            balance = CurrencyHandler.get_stripe_balance()

            # Find the currency in available balances
            for currency_balance in balance.available:
                if currency_balance["currency"].lower() == currency.lower():
                    available_cents = currency_balance["amount"]
                    has_sufficient = available_cents >= required_amount_cents

                    return {
                        "currency": currency.upper(),
                        "available_cents": available_cents,
                        "available_decimal": Decimal(available_cents) / 100,
                        "required_cents": required_amount_cents,
                        "required_decimal": Decimal(required_amount_cents) / 100,
                        "has_sufficient": has_sufficient,
                        "shortage_cents": max(0, required_amount_cents - available_cents),
                        "shortage_decimal": max(
                            Decimal("0"), (Decimal(required_amount_cents) - Decimal(available_cents)) / 100
                        ),
                    }

            # Currency not found in available balances
            return {
                "currency": currency.upper(),
                "available_cents": 0,
                "available_decimal": Decimal("0"),
                "required_cents": required_amount_cents,
                "required_decimal": Decimal(required_amount_cents) / 100,
                "has_sufficient": False,
                "shortage_cents": required_amount_cents,
                "shortage_decimal": Decimal(required_amount_cents) / 100,
            }

        except Exception as e:
            logger.error(f"Error checking currency balance: {e}")
            return {
                "currency": currency.upper(),
                "available_cents": 0,
                "available_decimal": Decimal("0"),
                "required_cents": required_amount_cents,
                "required_decimal": Decimal(required_amount_cents) / 100,
                "has_sufficient": False,
                "shortage_cents": required_amount_cents,
                "shortage_decimal": Decimal(required_amount_cents) / 100,
                "error": str(e),
            }

    @staticmethod
    def find_optimal_currency_for_transfer(preferred_currency: str, required_amount_cents: int) -> Dict:
        """
        Find the best currency to use for a transfer, considering balance and conversion rates.

        Args:
            preferred_currency (str): The originally requested currency
            required_amount_cents (int): Required amount in cents in the preferred currency

        Returns:
            dict: Optimal currency choice with conversion details
        """
        logger.info(f"Finding optimal currency for {required_amount_cents} cents in {preferred_currency}")

        # First check if preferred currency has sufficient balance
        preferred_check = CurrencyHandler.check_currency_balance(preferred_currency, required_amount_cents)

        if preferred_check["has_sufficient"]:
            logger.info(f"Sufficient balance in preferred currency {preferred_currency}")
            return {
                "success": True,
                "use_currency": preferred_currency.lower(),
                "use_currency_display": preferred_currency.upper(),
                "amount_cents": required_amount_cents,
                "amount_decimal": Decimal(required_amount_cents) / 100,
                "original_currency": preferred_currency.upper(),
                "conversion_needed": False,
                "exchange_rate": 1.0,
                "balance_info": preferred_check,
            }

        logger.warning(f"Insufficient balance in {preferred_currency}, looking for alternatives...")

        # Get available currencies sorted by balance
        available_currencies = CurrencyHandler.get_available_currencies_with_balance()

        if not available_currencies:
            logger.error("No currencies with available balance found")
            return {"success": False, "error": "No currencies with available balance", "balance_info": preferred_check}

        # Try each available currency, convert the required amount
        for currency_info in available_currencies:
            alt_currency = currency_info["currency_code"]
            available_cents = currency_info["amount_cents"]

            logger.info(f"Checking alternative currency {alt_currency} with balance: {available_cents} cents")

            # Convert required amount to this currency
            required_decimal = Decimal(required_amount_cents) / 100
            converted_amount, exchange_rate = CurrencyHandler.convert_currency(
                required_decimal, preferred_currency, alt_currency
            )

            converted_amount_cents = int(converted_amount * 100)

            if available_cents >= converted_amount_cents:
                logger.info(
                    f"Found suitable currency: {alt_currency} (converted amount: {converted_amount_cents} cents)"
                )

                return {
                    "success": True,
                    "use_currency": alt_currency,
                    "use_currency_display": alt_currency.upper(),
                    "amount_cents": converted_amount_cents,
                    "amount_decimal": converted_amount,
                    "original_currency": preferred_currency.upper(),
                    "original_amount_cents": required_amount_cents,
                    "original_amount_decimal": Decimal(required_amount_cents) / 100,
                    "conversion_needed": True,
                    "exchange_rate": exchange_rate,
                    "balance_info": {
                        "available_cents": available_cents,
                        "available_decimal": Decimal(available_cents) / 100,
                        "required_cents": converted_amount_cents,
                        "required_decimal": converted_amount,
                        "has_sufficient": True,
                    },
                }

        # No suitable currency found
        logger.error("No currency with sufficient balance found after conversion attempts")

        return {
            "success": False,
            "error": "Insufficient balance in all available currencies",
            "preferred_currency": preferred_currency.upper(),
            "required_amount_cents": required_amount_cents,
            "required_amount_decimal": Decimal(required_amount_cents) / 100,
            "available_currencies": available_currencies,
            "balance_info": preferred_check,
        }


def switch_currency(preferred_currency: str, required_amount_cents: int, destination_account_id: str) -> Dict:
    """
    Main function to handle currency switching for transfers with balance checking.

    Args:
        preferred_currency (str): Originally requested currency
        required_amount_cents (int): Required amount in cents in preferred currency
        destination_account_id (str): Stripe connected account ID

    Returns:
        dict: Currency switch result with optimal currency and conversion details
    """
    logger.info(f"Switch currency requested: {required_amount_cents} cents in {preferred_currency}")

    try:
        # Find optimal currency
        currency_result = CurrencyHandler.find_optimal_currency_for_transfer(preferred_currency, required_amount_cents)

        if not currency_result["success"]:
            logger.error(f"Currency switch failed: {currency_result.get('error', 'Unknown error')}")
            return currency_result

        # Check if destination account supports the selected currency
        try:
            provider = CurrencyHandler.get_provider()
            dest_account = provider.retrieve_account(destination_account_id)
            dest_country = dest_account.country

            # Log destination account info (could add currency compatibility check here)
            logger.info(
                f"Destination account country: {dest_country}, selected currency: {currency_result['use_currency']}"
            )

        except Exception as e:
            logger.warning(f"Could not verify destination account currency compatibility: {e}")

        # Check if conversion was needed and return simplified structure
        if currency_result["conversion_needed"]:
            logger.info(
                f"Currency conversion needed: {currency_result['original_currency']} to {currency_result['use_currency_display']} (rate: {currency_result['exchange_rate']})"
            )

            # Return simplified structure for conversions
            # Note: amount_decimal already contains the converted amount from find_optimal_currency_for_transfer
            return {
                "success": True,
                "was_converted": True,
                "original_currency": currency_result["original_currency"],
                "original_amount_cents": currency_result["original_amount_cents"],
                "original_amount_decimal": currency_result["original_amount_decimal"],
                "new_currency": currency_result["use_currency"],
                "new_amount_cents": currency_result["amount_cents"],
                "new_amount_decimal": currency_result["amount_decimal"],
                "rate": currency_result["exchange_rate"],
            }

        # Add transfer readiness info for non-conversion cases
        currency_result.update(
            {
                "success": True,
                "was_converted": False,
                "destination_account": destination_account_id,
                "recommendation": (
                    f"Use {currency_result['use_currency_display']} "
                    f"({currency_result['amount_decimal']:.2f}) "
                    f"(original currency)"
                ),
            }
        )

        logger.info(f"Currency switch successful: {currency_result['recommendation']}")

        return currency_result

    except ValueError as e:
        # Exchange rate errors
        logger.error(f"Exchange rate error in switch_currency: {e}")
        return {
            "success": False,
            "error": f"Exchange rate unavailable: {str(e)}",
            "error_type": "EXCHANGE_RATE_UNAVAILABLE",
            "preferred_currency": preferred_currency,
            "required_amount_cents": required_amount_cents,
            "message": "Please update exchange rate data or try again later.",
        }
    except Exception as e:
        logger.error(f"Unexpected error in switch_currency: {e}")
        return {
            "success": False,
            "error": f"Currency switch failed: {str(e)}",
            "error_type": "UNEXPECTED_ERROR",
            "preferred_currency": preferred_currency,
            "required_amount_cents": required_amount_cents,
        }
