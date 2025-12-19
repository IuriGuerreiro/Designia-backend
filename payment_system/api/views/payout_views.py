"""
PayoutViews.py - Dedicated views for payout-related functionality

This file contains all payout-related views and operations:
- Seller payout creation and management
- Seller money on hold tracking
- Payout order details and history
- Payout listing and detail views

Separated from main views.py to maintain clear separation of concerns.
Webhook handling remains in views.py for security isolation.
"""

import logging

from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payment_system.api.serializers.payment_serializers import PayoutSerializer, PayoutSummarySerializer
from payment_system.api.serializers.request_serializers import ReconciliationUpdateRequestSerializer
from payment_system.api.serializers.response_serializers import (
    ErrorResponseSerializer,
    PaymentHoldsResponseSerializer,
    PayoutAnalyticsResponseSerializer,
    PayoutDetailResponseSerializer,
    PayoutListResponseSerializer,
    PayoutOrdersResponseSerializer,
    PerformanceReportResponseSerializer,
    ReconciliationUpdateResponseSerializer,
)
from payment_system.domain.services.payout_service import PayoutService

# Import transaction utilities
from utils.transaction_utils import financial_transaction, retry_on_deadlock


# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()


# ===============================================================================
# HELPER FUNCTIONS
# ===============================================================================


def validate_2fa_requirement(user):
    """
    Validate that user has 2FA enabled for sensitive payout operations.

    OAuth users are exempt from this requirement as they use social auth.
    Regular users must have 2FA enabled to access payout functionality.

    Args:
        user: The authenticated user

    Returns:
        tuple: (is_valid: bool, error_response: Response or None)
    """
    # OAuth users are exempt from 2FA requirement
    if user.is_oauth_only_user():
        return True, None

    # Check if 2FA is enabled for non-OAuth users
    two_factor_enabled = getattr(user, "two_factor_enabled", False)

    if not two_factor_enabled:
        logger.warning(f"User {user.id} attempted to access payouts without 2FA enabled")
        return False, Response(
            {
                "error": "TWO_FACTOR_REQUIRED",
                "detail": "Two-factor authentication must be enabled to access payout functionality. Please enable 2FA in your account settings.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    return True, None


# ===============================================================================
# PAYOUT VIEWS - All payout-related functionality
# ===============================================================================

# ===============================================================================
# SELLER PAYOUT CREATION
# ===============================================================================


@extend_schema(
    operation_id="payout_create_seller_payout",
    summary="Create Seller Payout (Disabled)",
    description="Manual payout creation is disabled. This endpoint returns an error.",
    responses={
        410: OpenApiResponse(response=ErrorResponseSerializer, description="Payout creation disabled"),
    },
    tags=["Payouts"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def seller_payout(request):
    """Manual payout creation has been disabled.

    This endpoint now exists only to provide a clear error response
    indicating that manual payout creation is no longer supported.
    """
    logger.info("Seller payout endpoint called but manual creation is disabled")
    return Response(
        {
            "error": "PAYOUT_CREATION_DISABLED",
            "detail": "Manual payout creation is no longer available. Please contact support if you have questions.",
        },
        status=status.HTTP_410_GONE,
    )


@extend_schema(
    operation_id="payout_get_holds",
    summary="Get Payment Holds",
    description="Retrieve all held transactions for the authenticated seller. Requires 2FA to be enabled.",
    responses={
        200: OpenApiResponse(response=PaymentHoldsResponseSerializer, description="Holds retrieved"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Not authorized or 2FA not enabled"),
    },
    tags=["Payouts"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@financial_transaction
def get_seller_payment_holds(request):
    """
    Get all payment holds for the authenticated seller with remaining time calculation
    Using simplified PaymentTransaction model with integrated hold system
    """
    logger.info("[API] GET /stripe/holds/ called")

    if not request.user.is_authenticated:
        logger.warning("[ERROR] User not authenticated for stripe holds endpoint")
        return Response(
            {
                "error": "AUTHENTICATION_REQUIRED",
                "detail": "You must be logged in to view payment holds",
                "authenticated": False,
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        # Get user from database (don't trust token)
        user = User.objects.get(id=request.user.id)

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        # ROLE CHECK: Verify seller or admin role from database
        from utils.rbac import is_seller

        if not is_seller(user):
            logger.warning(
                f"Non-seller user {user.username} (ID: {user.id}, Role: {user.role}) attempted to access payment holds"
            )
            return Response(
                {
                    "error": "SELLER_ACCESS_REQUIRED",
                    "detail": "Permission denied. Only verified sellers can view payment holds.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        logger.info(f"[SUCCESS] Authenticated user: {user.username} (ID: {user.id})")

        # Use PayoutService to get the hold summary
        hold_summary_data = PayoutService.get_seller_hold_summary(str(user.id))

        if not hold_summary_data.get("success", False):
            return Response(
                {
                    "error": "PAYMENT_HOLDS_RETRIEVAL_FAILED",
                    "detail": hold_summary_data.get("message", "Failed to retrieve payment holds."),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = {
            "success": True,
            "summary": hold_summary_data["summary"],
            "holds": hold_summary_data["holds"],
            "message": hold_summary_data["message"],
            "debug_info": {
                "user_id": user.id,
                "username": user.username,
                "is_authenticated": True,
            },
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"[ERROR] Error retrieving seller payment holds for user {user.username}: {str(e)}")
        logger.error("[ERROR] Full exception: ", exc_info=True)
        return Response(
            {
                "error": "PAYMENT_HOLDS_RETRIEVAL_FAILED",
                "detail": f"Failed to retrieve payment holds: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ===============================================================================
# PAYOUT LIST AND DETAIL VIEWS
# ===============================================================================


@extend_schema(
    operation_id="payout_list",
    summary="List Payouts",
    description="List all payouts for the authenticated seller. Requires 2FA to be enabled.",
    parameters=[
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Results per page (default 20, max 100)",
        ),
        OpenApiParameter(
            name="offset", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, description="Pagination offset"
        ),
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by status (optional)",
        ),
        OpenApiParameter(
            name="from_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filter from date (YYYY-MM-DD)",
        ),
        OpenApiParameter(
            name="to_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filter to date (YYYY-MM-DD)",
        ),
    ],
    responses={
        200: OpenApiResponse(response=PayoutListResponseSerializer, description="List of payouts"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Not authorized or 2FA not enabled"),
    },
    tags=["Payouts"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@financial_transaction
def user_payouts_list(request):
    """
    Retrieve all payouts for the authenticated user (seller).
    Returns a paginated list of payouts with summary information.
    """
    try:
        # Get user from database (don't trust token)
        user = User.objects.get(id=request.user.id)

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        # ROLE CHECK: Verify seller or admin role from database
        from utils.rbac import is_seller

        if not is_seller(user):
            return Response(
                {
                    "error": "SELLER_ACCESS_REQUIRED",
                    "detail": "Permission denied. Only verified sellers can view payout history.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Using Service to get queryset
        # Note: Pagination is kept here in View as it's presentation logic
        service_result = PayoutService.get_seller_payouts_list(str(user.id), request.GET.dict())
        payouts = service_result.get("payouts_queryset", [])

        # Apply pagination if needed
        page_size = request.GET.get("page_size", 20)
        try:
            page_size = min(int(page_size), 100)  # Max 100 items per page
        except (ValueError, TypeError):
            page_size = 20

        # Simple offset-based pagination
        offset = 0
        try:
            offset = int(request.GET.get("offset", 0))
        except (ValueError, TypeError):
            offset = 0

        total_count = service_result.get("total_count", 0)
        payouts_page = payouts[offset : offset + page_size]

        serializer = PayoutSummarySerializer(payouts_page, many=True)

        response_data = {
            "payouts": serializer.data,
            "pagination": {
                "total_count": total_count,
                "offset": offset,
                "page_size": page_size,
                "has_next": (offset + page_size) < total_count,
                "has_previous": offset > 0,
            },
        }

        logger.info(f"Successfully retrieved {len(serializer.data)} payouts for user {user.id}")
        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error fetching payouts for user {request.user.id}: {str(e)}", exc_info=True)
        return Response(
            {"error": "PAYOUT_FETCH_ERROR", "detail": f"Failed to fetch payouts: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    operation_id="payout_detail",
    summary="Get Payout Detail",
    description="Get detailed information for a specific payout. Requires 2FA to be enabled.",
    responses={
        200: OpenApiResponse(response=PayoutDetailResponseSerializer, description="Payout detail"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Not authorized or 2FA not enabled"),
        404: OpenApiResponse(response=ErrorResponseSerializer, description="Payout not found"),
    },
    tags=["Payouts"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@financial_transaction
def payout_detail(request, payout_id):
    """
    Retrieve detailed information about a specific payout including all orders.
    Only accessible by the seller who owns the payout.
    """
    try:
        user = User.objects.get(id=request.user.id)

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        from utils.rbac import is_seller

        if not is_seller(user):
            return Response({"error": "SELLER_ACCESS_REQUIRED"}, status=status.HTTP_403_FORBIDDEN)

        result = PayoutService.get_seller_payout_detail(str(user.id), payout_id)
        payout = result.get("payout")

        if not payout:
            return Response(
                {"error": "PAYOUT_NOT_FOUND", "detail": "Payout not found or permission denied."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PayoutSerializer(payout)
        return Response({"payout": serializer.data}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error fetching payout detail {payout_id}: {str(e)}", exc_info=True)
        return Response(
            {"error": "PAYOUT_DETAIL_ERROR", "detail": f"Failed to fetch payout details: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@financial_transaction
@extend_schema(
    operation_id="payout_orders",
    summary="Get Payout Orders",
    description="List all orders included in a specific payout. Requires 2FA to be enabled.",
    responses={
        200: OpenApiResponse(response=PayoutOrdersResponseSerializer, description="Payout orders"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="Not authorized or 2FA not enabled"),
        404: OpenApiResponse(response=ErrorResponseSerializer, description="Payout not found"),
    },
    tags=["Payouts"],
)
def payout_orders(request, payout_id):
    """
    Retrieve all orders included in a specific payout.
    """
    try:
        user = User.objects.get(id=request.user.id)

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        from utils.rbac import is_seller

        if not is_seller(user):
            return Response({"error": "SELLER_ACCESS_REQUIRED"}, status=status.HTTP_403_FORBIDDEN)

        result = PayoutService.get_payout_orders(str(user.id), payout_id)
        payout_items = result.get("payout_items")
        payout = result.get("payout")

        if not payout or payout_items is None:
            return Response(
                {"error": "PAYOUT_NOT_FOUND", "detail": "Payout not found or permission denied."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Presentation logic (constructing the response dict) remains in View
        orders_data = []
        for item in payout_items:
            try:
                payment_transfer = item.payment_transfer
                order = payment_transfer.order if payment_transfer else None

                if order:
                    order_items = []
                    # Use prefetched user_items which are already filtered by product seller
                    user_order_items = getattr(order, "user_items", [])
                    for order_item in user_order_items:
                        order_items.append(
                            {
                                "product_name": order_item.product.name,
                                "quantity": order_item.quantity,
                                "price": str(order_item.unit_price),
                                "total": str(order_item.total_price),
                            }
                        )

                    order_data = {
                        "order_id": str(order.id),
                        "order_date": order.created_at.isoformat(),
                        "buyer_username": order.buyer.username,
                        "status": order.status,
                        "payment_status": order.payment_status,
                        "subtotal": str(order.subtotal),
                        "shipping_cost": str(order.shipping_cost),
                        "tax_amount": str(order.tax_amount),
                        "total_amount": str(order.total_amount),
                        "transfer_amount": str(item.transfer_amount),
                        "transfer_date": item.transfer_date.isoformat(),
                        "items": order_items,
                    }
                else:
                    order_data = {
                        "order_id": item.order_id,
                        "order_date": item.transfer_date.isoformat(),
                        "buyer_username": "Unknown",
                        "status": "completed",
                        "payment_status": "paid",
                        "total_amount": str(item.transfer_amount),
                        "transfer_amount": str(item.transfer_amount),
                        "transfer_date": item.transfer_date.isoformat(),
                        "item_names": item.item_names,
                        "items": [],
                    }

                orders_data.append(order_data)

            except Exception as e:
                logger.warning(f"Error processing payout item {item.id}: {str(e)}")
                continue

        response_data = {
            "payout_id": str(payout.id),
            "payout_amount": str(payout.amount_decimal),
            "payout_status": payout.status,
            "transfer_count": len(orders_data),
            "orders": orders_data,
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error fetching payout orders {payout_id}: {str(e)}", exc_info=True)
        return Response(
            {"error": "PAYOUT_ORDERS_ERROR", "detail": f"Failed to fetch payout orders: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ===============================================================================
# ENHANCED PAYOUT ANALYTICS AND REPORTING ENDPOINTS
# ===============================================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)
@extend_schema(
    operation_id="payout_analytics",
    summary="Payout Analytics",
    description="Get comprehensive payout analytics and metrics. Requires 2FA to be enabled.",
    responses={
        200: OpenApiResponse(response=PayoutAnalyticsResponseSerializer, description="Analytics data"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="2FA not enabled"),
        500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal error"),
    },
    tags=["Analytics"],
)
def payout_analytics_dashboard(request):
    """
    Comprehensive payout analytics dashboard with enhanced tracking metrics.
    """
    try:
        user = request.user

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        logger.info(f"Fetching payout analytics dashboard for user: {user.id}")

        analytics_data = PayoutService.get_analytics_dashboard(str(user.id))

        if "error" in analytics_data:
            return Response(analytics_data, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Successfully generated payout analytics for user {user.id}")
        return Response(analytics_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error generating payout analytics for user {request.user.id}: {str(e)}", exc_info=True)
        return Response(
            {
                "error": "PAYOUT_ANALYTICS_ERROR",
                "detail": f"Failed to generate payout analytics: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)
@extend_schema(
    operation_id="payout_performance",
    summary="Payout Performance Report",
    description="Get detailed performance metrics for payout operations. Requires 2FA to be enabled.",
    responses={
        200: OpenApiResponse(response=PerformanceReportResponseSerializer, description="Performance report"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="2FA not enabled"),
        500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal error"),
    },
    tags=["Analytics"],
)
def payout_performance_report(request):  # noqa: C901
    """
    Detailed performance report for payout operations with enhanced metrics.
    """
    try:
        user = request.user

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        logger.info(f"Generating performance report for user: {user.id}")

        report_data = PayoutService.get_performance_report(str(user.id))

        if "error" in report_data:
            return Response(report_data, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Successfully generated performance report for user {user.id}")
        return Response(report_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error generating performance report for user {request.user.id}: {str(e)}", exc_info=True)
        return Response(
            {
                "error": "PERFORMANCE_REPORT_ERROR",
                "detail": f"Failed to generate performance report: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)
@extend_schema(
    operation_id="payout_reconciliation_update",
    summary="Update Reconciliation Status",
    description="Update reconciliation status for a payout. Requires 2FA to be enabled.",
    request=ReconciliationUpdateRequestSerializer,
    responses={
        200: OpenApiResponse(response=ReconciliationUpdateResponseSerializer, description="Updated successfully"),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid status"),
        403: OpenApiResponse(response=ErrorResponseSerializer, description="2FA not enabled"),
        404: OpenApiResponse(response=ErrorResponseSerializer, description="Payout not found"),
    },
    tags=["Payouts"],
)
def update_payout_reconciliation(request, payout_id):
    """
    Update reconciliation status for a payout with enhanced tracking.
    """
    try:
        user = request.user

        # 2FA VALIDATION: Ensure user has 2FA enabled for payout access
        is_valid, error_response = validate_2fa_requirement(user)
        if not is_valid:
            return error_response

        new_status = request.data.get("reconciliation_status")
        notes = request.data.get("notes", "")

        if not new_status:
            return Response(
                {"error": "MISSING_RECONCILIATION_STATUS", "detail": "reconciliation_status field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_statuses = ["pending", "matched", "mismatched", "manual_review"]
        if new_status not in valid_statuses:
            return Response(
                {
                    "error": "INVALID_RECONCILIATION_STATUS",
                    "detail": f"Status must be one of: {', '.join(valid_statuses)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(f"Updating reconciliation status for payout {payout_id} to {new_status}")

        result = PayoutService.update_reconciliation(str(user.id), payout_id, new_status, notes)

        if not result.get("success"):
            return Response(
                {"error": result.get("error", "UPDATE_FAILED"), "detail": result.get("detail", "Update failed")},
                status=status.HTTP_404_NOT_FOUND
                if result.get("error") == "PAYOUT_NOT_FOUND"
                else status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(f"Successfully updated reconciliation status for payout {payout_id}")
        return Response(result, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error updating reconciliation for payout {payout_id}: {str(e)}", exc_info=True)
        return Response(
            {
                "error": "RECONCILIATION_UPDATE_ERROR",
                "detail": f"Failed to update reconciliation status: {str(e)}",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
