"""
AdminPayoutViews.py - Admin-only views for payout and transaction oversight

This file contains all admin-specific payout and transaction views:
- List all payouts across all sellers
- List all payment transactions
- View detailed payout information
- Monitor transaction status and holds

Security: All endpoints verify admin role from database (never trust token)
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payment_system.api.serializers.payment_serializers import PayoutSummarySerializer
from payment_system.domain.services.reporting_service import ReportingService  # Import ReportingService
from utils.rbac import is_admin
from utils.transaction_utils import financial_transaction  # Re-import financial_transaction


# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()

# ===============================================================================
# ADMIN PAYOUT OVERVIEW ENDPOINTS
# ===============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@financial_transaction
def admin_list_all_payouts(request):
    """
    Admin endpoint: List all payouts across all sellers with filtering and pagination.

    Query Parameters:
    - status: Filter by payout status (pending, paid, failed, etc.)
    - seller_id: Filter by specific seller
    - from_date: Filter payouts from this date (YYYY-MM-DD)
    - to_date: Filter payouts to this date (YYYY-MM-DD)
    - page_size: Number of results per page (default 50, max 200)
    - offset: Pagination offset
    - search: Search by seller username or email
    """
    try:
        # Get user from database (don't trust token)
        user = User.objects.get(id=request.user.id)

        # ADMIN CHECK: Verify admin role from database
        if not is_admin(user):
            logger.warning(
                f"Non-admin user {user.username} (ID: {user.id}, Role: {user.role}) attempted to access admin payouts list"
            )
            return Response(
                {
                    "error": "ADMIN_ACCESS_REQUIRED",
                    "detail": "Permission denied. Only administrators can view all payouts.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        logger.info(f"Admin {user.username} accessing all payouts list")

        filters = {
            "status": request.GET.get("status"),
            "seller_id": request.GET.get("seller_id"),
            "from_date": request.GET.get("from_date"),
            "to_date": request.GET.get("to_date"),
            "search": request.GET.get("search"),
        }
        # Clean filters from None values
        filters = {k: v for k, v in filters.items() if v is not None}

        # Get data from ReportingService
        report_data = ReportingService.get_payouts_summary(filters)
        payouts_queryset = report_data["payouts_queryset"]
        summary_stats = report_data["summary_stats"]
        status_breakdown = report_data["status_breakdown"]
        total_count = report_data["total_count"]

        # Pagination
        page_size = min(int(request.GET.get("page_size", 50)), 200)
        offset = int(request.GET.get("offset", 0))

        payouts_page = payouts_queryset[offset : offset + page_size]

        # Serialize payouts with seller information
        payouts_data = []
        for payout in payouts_page:
            payout_dict = PayoutSummarySerializer(payout).data
            # Add seller information
            payout_dict["seller_info"] = {
                "id": str(payout.seller.id),
                "username": payout.seller.username,
                "email": payout.seller.email,
                "first_name": payout.seller.first_name,
                "last_name": payout.seller.last_name,
                "role": payout.seller.role,
            }
            payouts_data.append(payout_dict)

        response_data = {
            "payouts": payouts_data,
            "pagination": {
                "total_count": total_count,
                "offset": offset,
                "page_size": page_size,
                "has_next": (offset + page_size) < total_count,
                "has_previous": offset > 0,
            },
            "summary": {
                "total_amount": str(summary_stats["total_amount"]),
                "average_amount": str(summary_stats["average_amount"]),
                "total_fees": str(summary_stats["total_fees"]),
                "status_breakdown": status_breakdown,
            },
        }

        logger.info(f"Admin {user.username} retrieved {len(payouts_data)} payouts")
        return Response(response_data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response(
            {"error": "USER_NOT_FOUND", "detail": "User not found in database."}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in admin_list_all_payouts: {str(e)}", exc_info=True)
        return Response(
            {"error": "ADMIN_PAYOUTS_LIST_ERROR", "detail": f"Failed to retrieve payouts: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@financial_transaction
def admin_list_all_transactions(request):  # noqa: C901
    """
    Admin endpoint: List all payment transactions across all sellers with filtering.

    Query Parameters:
    - status: Filter by transaction status (held, completed, released, etc.)
    - seller_id: Filter by specific seller
    - buyer_id: Filter by specific buyer
    - from_date: Filter transactions from this date
    - to_date: Filter transactions to this date
    - page_size: Number of results per page (default 50, max 200)
    - offset: Pagination offset
    - search: Search by seller/buyer username or order ID
    """
    try:
        # Get user from database (don't trust token)
        user = User.objects.get(id=request.user.id)

        # ADMIN CHECK: Verify admin role from database
        if not is_admin(user):
            logger.warning(
                f"Non-admin user {user.username} (ID: {user.id}, Role: {user.role}) attempted to access admin transactions list"
            )
            return Response(
                {
                    "error": "ADMIN_ACCESS_REQUIRED",
                    "detail": "Permission denied. Only administrators can view all transactions.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        logger.info(f"Admin {user.username} accessing all transactions list")

        filters = {
            "status": request.GET.get("status"),
            "seller_id": request.GET.get("seller_id"),
            "buyer_id": request.GET.get("buyer_id"),
            "from_date": request.GET.get("from_date"),
            "to_date": request.GET.get("to_date"),
            "search": request.GET.get("search"),
        }
        # Clean filters from None values
        filters = {k: v for k, v in filters.items() if v is not None}

        # Get data from ReportingService
        report_data = ReportingService.get_transaction_report(filters)
        transactions_queryset = report_data["transactions_queryset"]
        summary_stats = report_data["summary_stats"]
        status_breakdown = report_data["status_breakdown"]
        total_count = report_data["total_count"]

        # Pagination
        page_size = min(int(request.GET.get("page_size", 50)), 200)
        offset = int(request.GET.get("offset", 0))

        transactions_page = transactions_queryset[offset : offset + page_size]

        # Serialize transactions
        transactions_data = []
        for transaction in transactions_page:
            transaction_dict = {
                "id": str(transaction.id),
                "order_id": str(transaction.order.id) if transaction.order else None,
                "stripe_payment_intent_id": transaction.stripe_payment_intent_id,
                "status": transaction.status,
                "seller": {
                    "id": str(transaction.seller.id),
                    "username": transaction.seller.username,
                    "email": transaction.seller.email,
                },
                "buyer": (
                    {
                        "id": str(transaction.buyer.id),
                        "username": transaction.buyer.username,
                        "email": transaction.buyer.email,
                    }
                    if transaction.buyer
                    else None
                ),
                "amounts": {
                    "gross_amount": str(transaction.gross_amount),
                    "platform_fee": str(transaction.platform_fee),
                    "stripe_fee": str(transaction.stripe_fee),
                    "net_amount": str(transaction.net_amount),
                    "currency": transaction.currency,
                },
                "hold_info": {
                    "status": transaction.status,
                    "hold_reason": transaction.hold_reason,
                    "days_to_hold": transaction.days_to_hold,
                    "hold_start_date": (
                        transaction.hold_start_date.isoformat() if transaction.hold_start_date else None
                    ),
                    "planned_release_date": (
                        transaction.planned_release_date.isoformat() if transaction.planned_release_date else None
                    ),
                    "actual_release_date": (
                        transaction.actual_release_date.isoformat() if transaction.actual_release_date else None
                    ),
                },
                "payout_info": {
                    "payed_out": transaction.payed_out,
                },
                "timestamps": {
                    "created_at": transaction.created_at.isoformat(),
                    "updated_at": transaction.updated_at.isoformat(),
                    "purchase_date": transaction.purchase_date.isoformat() if transaction.purchase_date else None,
                },
            }
            transactions_data.append(transaction_dict)

        response_data = {
            "transactions": transactions_data,
            "pagination": {
                "total_count": total_count,
                "offset": offset,
                "page_size": page_size,
                "has_next": (offset + page_size) < total_count,
                "has_previous": offset > 0,
            },
            "summary": {
                "total_gross": str(summary_stats["total_gross"]),
                "total_net": str(summary_stats["total_net"]),
                "total_platform_fees": str(summary_stats["total_platform_fees"]),
                "total_stripe_fees": str(summary_stats["total_stripe_fees"]),
                "average_transaction": str(summary_stats["average_transaction"]),
                "status_breakdown": status_breakdown,
            },
        }

        logger.info(f"Admin {user.username} retrieved {len(transactions_data)} transactions")
        return Response(response_data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response(
            {"error": "USER_NOT_FOUND", "detail": "User not found in database."}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in admin_list_all_transactions: {str(e)}", exc_info=True)
        return Response(
            {"error": "ADMIN_TRANSACTIONS_LIST_ERROR", "detail": f"Failed to retrieve transactions: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
