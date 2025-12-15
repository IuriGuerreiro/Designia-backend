import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from marketplace.models import Order  # For order status
from payment_system.api.permissions import IsStaffOrInternalService
from payment_system.domain.services.payment_service import PaymentService
from payment_system.domain.services.payout_service import PayoutService


logger = logging.getLogger(__name__)
User = get_user_model()

# Initialize services
payment_service = PaymentService()
payout_service = PayoutService()


@api_view(["GET"])
@permission_classes([IsStaffOrInternalService])  # Custom internal permission
def get_payment_status_internal(request, order_id):
    """
    Internal API: Get payment status for a given order ID.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return Response({"error": "ORDER_NOT_FOUND", "detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    # Use cache for faster lookups
    cache_key = f"payment_status_order_{order_id}"
    cached_status = cache.get(cache_key)

    if cached_status:
        logger.info(f"Returning cached payment status for order {order_id}")
        return Response(cached_status, status=status.HTTP_200_OK)

    # If not in cache, retrieve from service
    result = payment_service.get_payment_status(order)

    if result.ok:
        response_data = {
            "order_id": str(order_id),
            "payment_status": result.value,
            "order_current_status": order.status,  # Also return order's own status for context
            "cached": False,
        }
        cache.set(cache_key, response_data, timeout=60)  # Cache for 60 seconds
        return Response(response_data, status=status.HTTP_200_OK)
    else:
        return Response(
            {"error": result.error, "detail": result.error_detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsStaffOrInternalService])  # Custom internal permission
def get_seller_balance_internal(request, seller_id):
    """
    Internal API: Get aggregate balance for a seller ID.
    """
    try:
        seller = User.objects.get(id=seller_id)
        if not seller.stripe_account_id:
            return Response(
                {"error": "NO_STRIPE_ACCOUNT", "detail": "Seller does not have a connected Stripe account."},
                status=status.HTTP_404_NOT_FOUND,
            )
    except User.DoesNotExist:
        return Response({"error": "SELLER_NOT_FOUND", "detail": "Seller not found."}, status=status.HTTP_404_NOT_FOUND)

    cache_key = f"seller_balance_{seller_id}"
    cached_balance = cache.get(cache_key)

    if cached_balance:
        logger.info(f"Returning cached seller balance for {seller_id}")
        return Response(cached_balance, status=status.HTTP_200_OK)

    try:
        # PayoutService already has get_account_balance (which uses StripePaymentProvider)
        # Note: PayoutService.get_seller_hold_summary gives holds, not just balance.
        # Let's use StripePaymentProvider directly for raw balance (as PaymentService does for platform balance).
        from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider

        provider = StripePaymentProvider()
        balance_data = provider.get_account_balance(seller.stripe_account_id)

        response_data = {
            "seller_id": str(seller_id),
            "available_balance": Decimal(balance_data.get("available", 0)) / 100,
            "pending_balance": Decimal(balance_data.get("pending", 0)) / 100,
            "currency": "USD",  # Assuming USD as base for now, should be dynamic
            "cached": False,
        }
        cache.set(cache_key, response_data, timeout=300)  # Cache for 5 minutes
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error retrieving seller balance for {seller_id}: {e}", exc_info=True)
        return Response(
            {"error": "BALANCE_RETRIEVAL_FAILED", "detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
