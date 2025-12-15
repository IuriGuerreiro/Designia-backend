import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.db.models import Avg, Sum
from django.utils import timezone

from payment_system.infra.observability.metrics import active_holds_value, payout_volume_total
from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider
from payment_system.models import PaymentTransaction, Payout, PayoutItem
from utils.transaction_utils import atomic_with_isolation


logger = logging.getLogger(__name__)

User = get_user_model()
payment_provider = StripePaymentProvider()


class PayoutService:
    @staticmethod
    def get_seller_hold_summary(user_id: str) -> Dict[str, Any]:
        """
        Retrieves and aggregates all payment holds for a given seller,
        calculating remaining time, progress percentage, and readiness for release.
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning(f"Seller with ID {user_id} not found for hold summary.")
            return {
                "summary": {},
                "holds": [],
                "message": f"Seller with ID {user_id} not found.",
            }

        held_transactions = PaymentTransaction.objects.filter(seller=user, status="held").select_related(
            "order", "buyer"
        )

        holds_data = []
        total_pending_amount = Decimal("0.00")
        now = timezone.now()

        for transaction in held_transactions:
            try:
                # Check if order is delivered before processing hold
                if transaction.order and transaction.order.status != "delivered":
                    logger.info(
                        f"Transaction {transaction.id} order {transaction.order.id} not delivered. Skipping hold processing."
                    )
                    continue

                # Calculate remaining time using integrated hold system
                if transaction.planned_release_date:
                    remaining_time = transaction.planned_release_date - now
                    remaining_days = max(0, remaining_time.days)
                    remaining_hours = max(0, remaining_time.seconds // 3600)

                    # Check if ready for release
                    is_ready_for_release = remaining_time.total_seconds() <= 0
                else:
                    # Fallback to days_to_hold and hold_start_date calculations
                    remaining_days = transaction.days_to_hold  # Assuming PaymentTransaction has this property directly
                    remaining_hours = 0  # Placeholder if not directly calculable from transaction properties
                    is_ready_for_release = False  # Placeholder if not directly calculable

                    # More accurate fallback:
                    if transaction.hold_start_date:
                        elapsed_time = now - transaction.hold_start_date
                        days_elapsed = elapsed_time.days
                        calculated_remaining_days = transaction.days_to_hold - days_elapsed
                        remaining_days = max(0, calculated_remaining_days)
                        if remaining_days == 0 and elapsed_time.total_seconds() >= (
                            transaction.days_to_hold * 24 * 3600
                        ):
                            is_ready_for_release = True
                        else:
                            is_ready_for_release = False
                    else:  # If no hold_start_date, assume not ready
                        is_ready_for_release = False
                        remaining_days = (
                            transaction.days_to_hold
                        )  # Still show total days to hold if start date missing

                # Parse item names for display (simplified from PaymentItems)
                item_list = transaction.item_names.split(", ") if transaction.item_names else []

                # Calculate progress percentage for UI
                total_hold_time_hours = transaction.days_to_hold * 24  # Convert to hours
                elapsed_hours = 0
                if transaction.hold_start_date:
                    elapsed_time = now - transaction.hold_start_date
                    elapsed_hours = elapsed_time.total_seconds() / 3600

                progress_percentage = (
                    min(100, max(0, (elapsed_hours / total_hold_time_hours) * 100)) if total_hold_time_hours > 0 else 0
                )

                hold_info = {
                    "transaction_id": str(transaction.id),
                    "order_id": str(transaction.order.id),
                    "buyer": {
                        "username": transaction.buyer.username,
                        "email": transaction.buyer.email,
                        "first_name": getattr(transaction.buyer, "first_name", ""),
                        "last_name": getattr(transaction.buyer, "last_name", ""),
                    },
                    "amounts": {
                        "gross_amount": float(transaction.gross_amount),
                        "platform_fee": float(transaction.platform_fee),
                        "stripe_fee": float(transaction.stripe_fee),
                        "net_amount": float(transaction.net_amount),
                        "currency": transaction.currency,
                    },
                    "order_details": {
                        "purchase_date": transaction.purchase_date.isoformat(),
                        "item_count": transaction.item_count,
                        "item_names": transaction.item_names,
                        "items": [{"product_name": name.strip(), "quantity": 1} for name in item_list],
                    },
                    "hold_status": {
                        "reason": transaction.hold_reason,
                        "reason_display": transaction.get_hold_reason_display(),  # Assuming this method exists
                        "status": "held",
                        "status_display": "Payment on Hold",
                        "total_hold_days": transaction.days_to_hold,
                        "hold_start_date": (
                            transaction.hold_start_date.isoformat() if transaction.hold_start_date else None
                        ),
                        "planned_release_date": (
                            transaction.planned_release_date.isoformat() if transaction.planned_release_date else None
                        ),
                        "remaining_days": remaining_days,
                        "remaining_hours": remaining_hours,
                        "progress_percentage": round(progress_percentage, 1),
                        "is_ready_for_release": is_ready_for_release,
                        "hold_notes": transaction.hold_notes
                        or f"Standard {transaction.days_to_hold}-day hold period for marketplace transactions",
                        "time_display": (
                            f"{remaining_days}d {remaining_hours}h remaining"
                            if not is_ready_for_release
                            else "Ready for release"
                        ),
                    },
                }

                holds_data.append(hold_info)
                total_pending_amount += transaction.net_amount

            except Exception as item_error:
                logger.error(f"Error processing transaction {transaction.id} for seller {user.id}: {str(item_error)}")
                continue

        # Summary statistics
        summary = {
            "total_holds": len(holds_data),
            "total_pending_amount": str(total_pending_amount),
            "currency": "USD",  # Assuming USD as default
            "ready_for_release_count": sum(1 for hold in holds_data if hold["hold_status"]["is_ready_for_release"]),
        }

        logger.info(
            f"Successfully prepared hold summary with {len(holds_data)} holds, total pending: ${total_pending_amount}"
        )
        # Set gauge for active holds
        active_holds_value.labels(currency="USD").set(float(total_pending_amount))

        return {
            "success": True,
            "summary": summary,
            "holds": holds_data,
            "message": f"Found {len(holds_data)} payment holds for seller {user.username}.",
        }

    @staticmethod
    def get_seller_payouts_list(user_id: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieves all payouts for a specific seller with filtering and pagination.
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning(f"Seller with ID {user_id} not found for payouts list.")
            return {"payouts": [], "pagination": {"total_count": 0}}

        payouts = Payout.objects.filter(seller=user).order_by("-created_at")

        # Apply filters (if any)
        # Add filtering logic similar to ReportingService if needed for seller-specific filters

        total_count = payouts.count()
        # Pagination to be handled by the view, return queryset
        return {
            "payouts_queryset": payouts,
            "total_count": total_count,
        }

    @staticmethod
    def get_seller_payout_detail(user_id: str, payout_id: str) -> Dict[str, Any]:
        """
        Retrieves detailed information about a specific payout for a seller.
        """
        try:
            user = User.objects.get(id=user_id)
            payout = Payout.objects.prefetch_related("payout_items__payment_transfer__order").get(
                id=payout_id, seller=user
            )
            return {"payout": payout}
        except User.DoesNotExist:
            logger.warning(f"Seller with ID {user_id} not found for payout detail {payout_id}.")
            return {}
        except Payout.DoesNotExist:
            logger.warning(f"Payout {payout_id} not found for seller {user_id} or permission denied.")
            return {}

    @staticmethod
    def get_payout_orders(user_id: str, payout_id: str) -> Dict[str, Any]:
        """
        Retrieves all orders included in a specific payout, filtered by seller ownership.
        """
        try:
            user = User.objects.get(id=user_id)
            payout = Payout.objects.get(id=payout_id, seller=user)

            from django.db.models import Prefetch

            from marketplace.models import OrderItem

            payout_items = (
                PayoutItem.objects.filter(payout=payout)
                .select_related("payment_transfer__order__buyer")
                .prefetch_related(
                    Prefetch(
                        "payment_transfer__order__items",
                        queryset=OrderItem.objects.filter(product__seller=user).select_related("product"),
                        to_attr="user_items",
                    )
                )
                .order_by("-transfer_date")
            )
            return {"payout_items": payout_items, "payout": payout}
        except User.DoesNotExist:
            logger.warning(f"Seller with ID {user_id} not found for payout orders {payout_id}.")
            return {}
        except Payout.DoesNotExist:
            logger.warning(f"Payout {payout_id} not found for seller {user_id} or permission denied.")
            return {}

    @staticmethod
    def get_analytics_dashboard(user_id: str) -> Dict[str, Any]:
        """
        Generates comprehensive payout analytics dashboard with enhanced tracking metrics.
        Uses READ COMMITTED isolation.
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return {"error": "User not found"}

        with atomic_with_isolation("READ COMMITTED"):
            # Performance tracking
            start_time = timezone.now()

            # Get all payouts for analytics
            payouts = Payout.objects.filter(seller=user).select_related().order_by("-created_at")

            # Basic statistics
            total_payouts = payouts.count()
            successful_payouts = payouts.filter(status="paid").count()
            failed_payouts = payouts.filter(status="failed").count()
            pending_payouts = payouts.filter(status__in=["pending", "in_transit"]).count()

            # Financial metrics
            financial_metrics = payouts.aggregate(
                total_amount=Sum("amount_decimal"), average_payout=Avg("amount_decimal"), total_fees=Sum("total_fees")
            )

            # Processing performance metrics
            completed_payouts = payouts.filter(processing_completed_at__isnull=False)
            processing_times = []

            for payout in completed_payouts[:50]:  # Last 50 for analysis
                if payout.processing_duration_ms:
                    processing_times.append(payout.processing_duration_ms)

            avg_processing_time_ms = sum(processing_times) / len(processing_times) if processing_times else 0

            # Reconciliation status breakdown
            reconciliation_stats = {}
            for status, display_name in Payout._meta.get_field("reconciliation_status").choices:
                count = payouts.filter(reconciliation_status=status).count()
                reconciliation_stats[status] = {
                    "count": count,
                    "display_name": display_name,
                    "percentage": (count / total_payouts * 100) if total_payouts > 0 else 0,
                }

            # Recent activity (last 30 days)
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_payouts = payouts.filter(created_at__gte=thirty_days_ago)

            # Error analysis
            error_analysis = {"deadlock_retries": 0, "stripe_failures": 0, "transaction_errors": 0, "total_retries": 0}

            for payout in payouts[:100]:  # Analyze last 100 payouts
                error_analysis["total_retries"] += payout.retry_count
                if payout.failure_code:
                    error_analysis["stripe_failures"] += 1
                if payout.performance_metrics:
                    metrics = payout.performance_metrics.get("metrics", [])
                    for metric in metrics:
                        if "error" in metric.get("name", "").lower():
                            error_analysis["transaction_errors"] += 1

            # Calculate query performance
            query_duration = (timezone.now() - start_time).total_seconds() * 1000

            analytics_data = {
                "summary": {
                    "total_payouts": total_payouts,
                    "successful_payouts": successful_payouts,
                    "failed_payouts": failed_payouts,
                    "pending_payouts": pending_payouts,
                    "success_rate": (successful_payouts / total_payouts * 100) if total_payouts > 0 else 0,
                    "failure_rate": (failed_payouts / total_payouts * 100) if total_payouts > 0 else 0,
                },
                "financial_metrics": {
                    "total_amount": str(financial_metrics["total_amount"] or 0),
                    "average_payout": str(financial_metrics["average_payout"] or 0),
                    "total_fees": str(financial_metrics["total_fees"] or 0),
                    "currency": "EUR",
                },
                "performance_metrics": {
                    "average_processing_time_ms": round(avg_processing_time_ms, 2),
                    "average_processing_time_formatted": (
                        f"{avg_processing_time_ms / 1000:.1f}s"
                        if avg_processing_time_ms > 1000
                        else f"{avg_processing_time_ms:.0f}ms"
                    ),
                    "total_processing_samples": len(processing_times),
                    "query_time_ms": round(query_duration, 2),
                    "isolation_level": "READ_COMMITTED",
                },
                "reconciliation_status": reconciliation_stats,
                "recent_activity": {
                    "last_30_days": recent_payouts.count(),
                    "recent_success_rate": (
                        (recent_payouts.filter(status="paid").count() / recent_payouts.count() * 100)
                        if recent_payouts.count() > 0
                        else 0
                    ),
                    "recent_average_amount": str(recent_payouts.aggregate(avg=Avg("amount_decimal"))["avg"] or 0),
                },
                "error_analysis": error_analysis,
                "tracking_capabilities": {
                    "status_history_enabled": True,
                    "performance_metrics_enabled": True,
                    "reconciliation_tracking_enabled": True,
                    "retry_tracking_enabled": True,
                    "enhanced_error_tracking": True,
                },
            }

            return analytics_data

    @staticmethod
    def get_performance_report(user_id: str) -> Dict[str, Any]:
        """
        Generates detailed performance report for payout operations.
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return {"error": "User not found"}

        with atomic_with_isolation("READ COMMITTED"):
            start_time = timezone.now()

            # Get payouts with performance data
            payouts_with_metrics = Payout.objects.filter(seller=user, performance_metrics__isnull=False).order_by(
                "-created_at"
            )[:100]  # Last 100 with metrics

            performance_data = {
                "processing_times": [],
                "query_times": [],
                "error_counts": [],
                "retry_analysis": [],
                "isolation_level_compliance": 0,
            }

            total_analyzed = 0

            for payout in payouts_with_metrics:
                total_analyzed += 1

                # Extract performance metrics
                if payout.performance_metrics and "metrics" in payout.performance_metrics:
                    metrics = payout.performance_metrics["metrics"]

                    for metric in metrics:
                        metric_name = metric.get("name", "")
                        metric_value = metric.get("value", 0)

                        if "duration" in metric_name.lower() and "ms" in metric_name:
                            performance_data["processing_times"].append(
                                {
                                    "payout_id": str(payout.id)[:8],
                                    "metric_name": metric_name,
                                    "duration_ms": metric_value,
                                    "timestamp": metric.get("timestamp"),
                                }
                            )

                        elif "query" in metric_name.lower():
                            performance_data["query_times"].append(
                                {
                                    "payout_id": str(payout.id)[:8],
                                    "query_type": metric_name,
                                    "duration_ms": metric_value,
                                }
                            )

                        elif "error" in metric_name.lower():
                            performance_data["error_counts"].append(
                                {
                                    "payout_id": str(payout.id)[:8],
                                    "error_type": metric_name,
                                    "error_details": str(metric_value),
                                    "timestamp": metric.get("timestamp"),
                                }
                            )

                # Analyze retry patterns
                if payout.retry_count > 0:
                    performance_data["retry_analysis"].append(
                        {
                            "payout_id": str(payout.id)[:8],
                            "retry_count": payout.retry_count,
                            "last_retry": payout.last_retry_at.isoformat() if payout.last_retry_at else None,
                            "final_status": payout.status,
                            "reconciliation_status": payout.reconciliation_status,
                        }
                    )

            # Calculate aggregated metrics
            processing_times = [item["duration_ms"] for item in performance_data["processing_times"]]
            query_times = [item["duration_ms"] for item in performance_data["query_times"]]

            report_data = {
                "report_metadata": {
                    "generated_at": timezone.now().isoformat(),
                    "payouts_analyzed": total_analyzed,
                    "report_generation_time_ms": round((timezone.now() - start_time).total_seconds() * 1000, 2),
                    "isolation_level": "READ_COMMITTED",
                    "deadlock_retry_enabled": True,
                },
                "processing_performance": {
                    "average_processing_time_ms": (
                        round(sum(processing_times) / len(processing_times), 2) if processing_times else 0
                    ),
                    "median_processing_time_ms": (
                        sorted(processing_times)[len(processing_times) // 2] if processing_times else 0
                    ),
                    "max_processing_time_ms": max(processing_times) if processing_times else 0,
                    "min_processing_time_ms": min(processing_times) if processing_times else 0,
                    "total_samples": len(processing_times),
                },
                "query_performance": {
                    "average_query_time_ms": round(sum(query_times) / len(query_times), 2) if query_times else 0,
                    "total_query_samples": len(query_times),
                    "query_breakdown": performance_data["query_times"][:10],  # Top 10 for analysis
                },
                "error_analysis": {
                    "total_errors": len(performance_data["error_counts"]),
                    "error_rate": (
                        (len(performance_data["error_counts"]) / total_analyzed * 100) if total_analyzed > 0 else 0
                    ),
                    "recent_errors": performance_data["error_counts"][:5],  # Most recent errors
                },
                "retry_analysis": {
                    "payouts_with_retries": len(performance_data["retry_analysis"]),
                    "retry_rate": (
                        (len(performance_data["retry_analysis"]) / total_analyzed * 100) if total_analyzed > 0 else 0
                    ),
                    "total_retry_attempts": sum([item["retry_count"] for item in performance_data["retry_analysis"]]),
                    "retry_details": performance_data["retry_analysis"][:10],  # Top 10 for analysis
                },
                "recommendations": [],
            }

            # Generate performance recommendations
            avg_processing = report_data["processing_performance"]["average_processing_time_ms"]
            if avg_processing > 5000:  # > 5 seconds
                report_data["recommendations"].append(
                    "Consider optimizing payout creation process - average processing time is high"
                )

            error_rate = report_data["error_analysis"]["error_rate"]
            if error_rate > 10:  # > 10% error rate
                report_data["recommendations"].append(
                    "High error rate detected - review error tracking and implement fixes"
                )

            retry_rate = report_data["retry_analysis"]["retry_rate"]
            if retry_rate > 5:  # > 5% retry rate
                report_data["recommendations"].append(
                    "Consider database optimization - high retry rate suggests deadlock issues"
                )

            if not report_data["recommendations"]:
                report_data["recommendations"].append("Payout performance is within acceptable ranges")

            return report_data

    @staticmethod
    def update_reconciliation(user_id: str, payout_id: str, new_status: str, notes: str) -> Dict[str, Any]:
        """
        Update reconciliation status for a payout with enhanced tracking.
        """
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return {"success": False, "error": "User not found"}

        with atomic_with_isolation("READ COMMITTED"):
            start_time = timezone.now()

            # Get payout with proper locking (Payout model first)
            try:
                payout = Payout.objects.select_for_update().get(id=payout_id, seller=user)
            except Payout.DoesNotExist:
                return {
                    "success": False,
                    "error": "PAYOUT_NOT_FOUND",
                    "detail": "Payout not found or you do not have permission to update it.",
                }

            # Track performance
            old_status = payout.reconciliation_status

            # Update reconciliation status using the enhanced tracking method
            payout.update_reconciliation_status(new_status, notes)

            if new_status == "paid":
                payout_volume_total.labels(currency=payout.currency, status="paid").inc(float(payout.amount_decimal))

            # Track the operation performance
            operation_duration = (timezone.now() - start_time).total_seconds() * 1000

            return {
                "success": True,
                "payout_id": str(payout.id),
                "reconciliation_update": {
                    "old_status": old_status,
                    "new_status": new_status,
                    "updated_at": payout.reconciled_at.isoformat() if payout.reconciled_at else None,
                    "notes": notes,
                    "updated_by": user.username,
                },
                "performance_metrics": {
                    "operation_duration_ms": round(operation_duration, 2),
                    "isolation_level": "READ_COMMITTED",
                    "model_ordering": "Payout (select_for_update)",
                    "deadlock_retry_enabled": True,
                },
                "status_history": {
                    "total_entries": len(payout.status_history) if payout.status_history else 0,
                    "latest_entry": payout.latest_status_change,
                },
            }
