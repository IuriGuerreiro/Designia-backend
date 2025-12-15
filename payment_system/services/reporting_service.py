import logging
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.db.models import Avg, Q, Sum

from ..models import PaymentTransaction, Payout


logger = logging.getLogger(__name__)

User = get_user_model()


class ReportingService:
    @staticmethod
    def get_payouts_summary(filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregates payout data based on status, date range, seller, search query.
        Returns: { 'total_count': ..., 'payouts': [...], 'summary_stats': {...}, 'status_breakdown': {...} }
        """
        logger.info(f"ReportingService: Getting payouts summary with filters: {filters}")

        payouts = Payout.objects.select_related("seller").all()

        # Apply filters
        if "status" in filters:
            payouts = payouts.filter(status=filters["status"])
        if "seller_id" in filters:
            payouts = payouts.filter(seller_id=filters["seller_id"])
        if "from_date" in filters:
            payouts = payouts.filter(created_at__gte=filters["from_date"])
        if "to_date" in filters:
            payouts = payouts.filter(created_at__lte=filters["to_date"])
        if "search" in filters:
            search_query = filters["search"]
            payouts = payouts.filter(
                Q(seller__username__icontains=search_query)
                | Q(seller__email__icontains=search_query)
                | Q(seller__first_name__icontains=search_query)
                | Q(seller__last_name__icontains=search_query)
            )

        # Order by most recent first
        payouts = payouts.order_by("-created_at")

        total_count = payouts.count()

        # Summary statistics
        summary_stats = payouts.aggregate(
            total_amount=Sum("amount_decimal"), average_amount=Avg("amount_decimal"), total_fees=Sum("total_fees")
        )

        # Status breakdown
        status_breakdown = {}
        for status_choice, _ in Payout._meta.get_field("status").choices:
            count = payouts.filter(status=status_choice).count()
            status_breakdown[status_choice] = count

        # Return the queryset and summary data, pagination will be handled by the view
        # We'll return full payouts here, the view can handle serialization and pagination slicing
        return {
            "total_count": total_count,
            "payouts_queryset": payouts,  # Return queryset for later pagination and serialization in view
            "summary_stats": {
                "total_amount": summary_stats["total_amount"] or Decimal("0.00"),
                "average_amount": summary_stats["average_amount"] or Decimal("0.00"),
                "total_fees": summary_stats["total_fees"] or Decimal("0.00"),
            },
            "status_breakdown": status_breakdown,
        }

    @staticmethod
    def get_transaction_report(filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregates transaction data based on status, seller, buyer, date range, search query.
        Returns: { 'total_count': ..., 'transactions': [...], 'summary_stats': {...}, 'status_breakdown': {...} }
        """
        logger.info(f"ReportingService: Getting transaction report with filters: {filters}")

        transactions = PaymentTransaction.objects.select_related("seller", "buyer", "order").all()

        # Apply filters
        if "status" in filters:
            transactions = transactions.filter(status=filters["status"])
        if "seller_id" in filters:
            transactions = transactions.filter(seller_id=filters["seller_id"])
        if "buyer_id" in filters:
            transactions = transactions.filter(buyer_id=filters["buyer_id"])
        if "from_date" in filters:
            transactions = transactions.filter(created_at__gte=filters["from_date"])
        if "to_date" in filters:
            transactions = transactions.filter(created_at__lte=filters["to_date"])
        if "search" in filters:
            search_query = filters["search"]
            transactions = transactions.filter(
                Q(seller__username__icontains=search_query)
                | Q(buyer__username__icontains=search_query)
                | Q(order__id__icontains=search_query)
                | Q(stripe_payment_intent_id__icontains=search_query)
            )

        # Order by most recent first
        transactions = transactions.order_by("-created_at")

        total_count = transactions.count()

        # Summary statistics
        summary_stats = transactions.aggregate(
            total_gross=Sum("gross_amount"),
            total_net=Sum("net_amount"),
            total_platform_fees=Sum("platform_fee"),
            total_stripe_fees=Sum("stripe_fee"),
            average_transaction=Avg("gross_amount"),
        )

        # Status breakdown
        status_breakdown = {}
        for status_choice in [
            "held",
            "completed",
            "released",
            "failed",
            "refunded",
        ]:  # Assuming these are the primary statuses
            count = transactions.filter(status=status_choice).count()
            status_breakdown[status_choice] = count

        return {
            "total_count": total_count,
            "transactions_queryset": transactions,  # Return queryset for later pagination and serialization in view
            "summary_stats": {
                "total_gross": summary_stats["total_gross"] or Decimal("0.00"),
                "total_net": summary_stats["total_net"] or Decimal("0.00"),
                "total_platform_fees": summary_stats["total_platform_fees"] or Decimal("0.00"),
                "total_stripe_fees": summary_stats["total_stripe_fees"] or Decimal("0.00"),
                "average_transaction": summary_stats["average_transaction"] or Decimal("0.00"),
            },
            "status_breakdown": status_breakdown,
        }
