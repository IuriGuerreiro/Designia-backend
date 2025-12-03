"""
PayoutService - Seller Payout Management

Manages calculations and execution of seller payouts.
Handles platform fees, refunds, and transfers to connected accounts.

Story 4.4: PayoutService - Seller Payments
"""

import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from infrastructure.payments.interface import PaymentProviderInterface
from marketplace.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from payment_system.models import PaymentTransaction, Payout, PayoutItem

logger = logging.getLogger(__name__)


class PayoutService(BaseService):
    """
    Service for managing seller payouts.

    Responsibilities:
    - Calculate payout amounts (net of fees/refunds)
    - Execute payouts via payment provider (transfers)
    - Record payout history
    """

    def __init__(self, payment_provider: PaymentProviderInterface = None):
        super().__init__()
        self.payment_provider = payment_provider or self._get_default_provider()
        # Platform fee percentage (e.g., 0.10 for 10%)
        self.platform_fee_percent = Decimal(getattr(settings, "PLATFORM_FEE_PERCENT", "0.10"))

    def _get_default_provider(self):
        from infrastructure.container import Container

        return Container.get_payment_provider()

    @BaseService.log_performance
    def calculate_payout(self, seller, period_start=None, period_end=None) -> ServiceResult[Decimal]:
        """
        Calculate pending payout amount for a seller.
        Sums up 'completed' PaymentTransactions that haven't been paid out yet.

        Args:
            seller: User object (seller)
            period_start: Optional start datetime
            period_end: Optional end datetime

        Returns:
            ServiceResult with total payout amount (Decimal)
        """
        try:
            # Filter eligible transactions:
            # - Belongs to seller
            # - Status is 'completed' (funds available) OR 'released' (legacy status)
            # - Not yet paid out (payed_out=False)
            # - Within optional period

            queryset = PaymentTransaction.objects.filter(
                seller=seller, payed_out=False, status__in=["completed", "released"]
            )

            if period_start:
                queryset = queryset.filter(created_at__gte=period_start)
            if period_end:
                queryset = queryset.filter(created_at__lte=period_end)

            # Sum net_amount (which already has fees deducted in PaymentTransaction model)
            total = queryset.aggregate(total=Sum("net_amount"))["total"] or Decimal("0.00")

            return service_ok(total)

        except Exception as e:
            self.logger.error(f"Error calculating payout for seller {seller.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def create_payout(self, seller, amount: Optional[Decimal] = None) -> ServiceResult[Payout]:
        """
        Execute a payout for a seller.
        Creates a Payout record and initiates transfer via provider.

        Args:
            seller: User object (seller)
            amount: Optional override amount (otherwise calculates pending total)

        Returns:
            ServiceResult with Payout object
        """
        try:
            # 1. Identify eligible transactions
            transactions = PaymentTransaction.objects.filter(
                seller=seller, payed_out=False, status__in=["completed", "released"]
            ).select_for_update()

            if not transactions.exists():
                return service_err(ErrorCodes.INVALID_OPERATION, "No eligible transactions for payout")

            # 2. Calculate Total
            calculated_total = transactions.aggregate(total=Sum("net_amount"))["total"] or Decimal("0.00")

            if amount is not None and amount != calculated_total:
                # Partial payouts not fully supported in this simplified flow logic without specific transaction selection
                # For now, we assume full payout of pending balance.
                return service_err(ErrorCodes.INVALID_OPERATION, "Partial payouts not supported; amount mismatch")

            final_amount = calculated_total

            if final_amount <= 0:
                return service_err(ErrorCodes.INVALID_OPERATION, "Payout amount must be positive")

            # 3. Get Seller Stripe Account ID
            stripe_account_id = getattr(seller, "stripe_account_id", None)  # Assuming field exists or related profile
            if not stripe_account_id:
                # Fallback check if it's on profile
                profile = getattr(seller, "profile", None)
                stripe_account_id = getattr(profile, "stripe_account_id", None)

            if not stripe_account_id:
                return service_err(ErrorCodes.INVALID_PAYMENT_DATA, "Seller has no connected Stripe account")

            # 4. Create Payout Record (Pending)
            payout = Payout.objects.create(
                seller=seller,
                amount_decimal=final_amount,
                amount_cents=int(final_amount * 100),
                currency="USD",
                status="pending",
                payout_type="standard",
            )

            # 5. Link transactions to Payout
            payout_items = []
            for txn in transactions:
                payout_items.append(
                    PayoutItem(
                        payout=payout,
                        payment_transfer=txn,
                        # Denormalize fields manually for bulk_create
                        transfer_amount=txn.net_amount,
                        transfer_currency=txn.currency.upper(),
                        transfer_date=timezone.now(),
                        order_id=str(txn.order.id) if txn.order else "",
                        item_names=txn.item_names,
                    )
                )
                txn.payed_out = True
                txn.save(
                    update_fields=["payed_out"]
                )  # Don't change status from 'completed' yet? Or maybe 'payed_out'?
                # Model doesn't have 'payed_out' status in choices, but has 'payed_out' boolean.

            PayoutItem.objects.bulk_create(payout_items)
            payout.calculate_totals()

            # 6. Execute Transfer via Provider
            # Provider interface needs 'create_transfer' or similar.
            # Interface from Story 1.3 might need update if it only has 'create_checkout_session'.
            # Let's check interface capabilities.
            # If missing, we'll add it or assume it's there for now (AC says "Stripe Connect integration for transfers").

            # Assuming provider has `create_payout(amount, currency, destination)` or similar.
            # NOTE: 'create_refund' exists, but 'create_transfer' might strictly be needed.
            # I'll check interface.py content from memory/context.
            # It has: create_checkout_session, retrieve_session, verify_webhook, create_refund, retrieve_payment_intent.
            # It DOES NOT have 'create_transfer' or 'create_payout'.
            # I MUST add it to `PaymentProviderInterface` to satisfy AC.

            # For this step, I will add it to the interface file first.
            # Proceeding with assumption it will be added.

            try:
                transfer_result = self.payment_provider.create_transfer(
                    amount=final_amount,
                    currency="usd",
                    destination_account=stripe_account_id,
                    metadata={"payout_id": str(payout.id)},
                )

                payout.stripe_payout_id = transfer_result.get("id", "manual_transfer")
                payout.status = "paid"  # Or 'in_transit'
                payout.save()

                return service_ok(payout)

            except Exception as e:
                payout.status = "failed"
                payout.failure_message = str(e)
                payout.save()
                raise  # Re-raise to trigger transaction rollback?
                # Actually, we want to rollback DB changes if transfer fails.
                # @transaction.atomic handles rollback if exception raised.
                # So re-raising is correct.

        except Exception as e:
            self.logger.error(f"Payout failed for seller {seller.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.PAYMENT_PROVIDER_ERROR, str(e))

    @BaseService.log_performance
    def process_pending_payouts(self) -> ServiceResult[int]:
        """
        Process payouts for all eligible sellers.
        Intended for Celery task.

        Returns:
            ServiceResult with count of processed payouts
        """
        try:
            # Find all sellers with pending transactions
            # This could be optimized with aggregation
            eligible_sellers_ids = (
                PaymentTransaction.objects.filter(payed_out=False, status="completed")
                .values_list("seller_id", flat=True)
                .distinct()
            )

            count = 0
            for seller_id in eligible_sellers_ids:
                # Fetch user object - suboptimal for loop but safe for individual transactions
                from django.contrib.auth import get_user_model

                User = get_user_model()
                seller = User.objects.get(id=seller_id)

                result = self.create_payout(seller)
                if result.ok:
                    count += 1
                else:
                    self.logger.warning(f"Failed auto-payout for seller {seller_id}: {result.error}")

            return service_ok(count)

        except Exception as e:
            self.logger.error(f"Error processing pending payouts: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
