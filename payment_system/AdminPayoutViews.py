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
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from authentication.permissions import AdminRequired

from .models import Payout, PayoutItem, PaymentTransaction, PaymentTracker
from .serializers import PayoutSerializer, PayoutSummarySerializer
from marketplace.models import Order

# Import transaction utilities
from utils.transaction_utils import financial_transaction

# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()

# ===============================================================================
# ADMIN PAYOUT OVERVIEW ENDPOINTS
# ===============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated, AdminRequired])
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
        # Re-fetch the admin from the database for logging/auditing.
        user = User.objects.get(id=request.user.id)
        logger.info(f"Admin {user.username} accessing all payouts list")

        # Start with all payouts
        payouts = Payout.objects.select_related('seller').all()

        # Apply filters
        payout_status = request.GET.get('status')
        if payout_status:
            payouts = payouts.filter(status=payout_status)

        seller_id = request.GET.get('seller_id')
        if seller_id:
            payouts = payouts.filter(seller_id=seller_id)

        from_date = request.GET.get('from_date')
        if from_date:
            payouts = payouts.filter(created_at__gte=from_date)

        to_date = request.GET.get('to_date')
        if to_date:
            payouts = payouts.filter(created_at__lte=to_date)

        search = request.GET.get('search')
        if search:
            payouts = payouts.filter(
                Q(seller__username__icontains=search) |
                Q(seller__email__icontains=search) |
                Q(seller__first_name__icontains=search) |
                Q(seller__last_name__icontains=search)
            )

        # Order by most recent first
        payouts = payouts.order_by('-created_at')

        # Pagination
        page_size = min(int(request.GET.get('page_size', 50)), 200)
        offset = int(request.GET.get('offset', 0))

        total_count = payouts.count()
        payouts_page = payouts[offset:offset + page_size]

        # Serialize payouts with seller information
        payouts_data = []
        for payout in payouts_page:
            payout_dict = PayoutSummarySerializer(payout).data
            # Add seller information
            payout_dict['seller_info'] = {
                'id': str(payout.seller.id),
                'username': payout.seller.username,
                'email': payout.seller.email,
                'first_name': payout.seller.first_name,
                'last_name': payout.seller.last_name,
                'role': payout.seller.role,
            }
            payouts_data.append(payout_dict)

        # Calculate summary statistics
        summary_stats = payouts.aggregate(
            total_amount=Sum('amount_decimal'),
            average_amount=Avg('amount_decimal'),
            total_fees=Sum('total_fees')
        )

        status_breakdown = {}
        for status_choice, _ in Payout._meta.get_field('status').choices:
            count = payouts.filter(status=status_choice).count()
            status_breakdown[status_choice] = count

        response_data = {
            'payouts': payouts_data,
            'pagination': {
                'total_count': total_count,
                'offset': offset,
                'page_size': page_size,
                'has_next': (offset + page_size) < total_count,
                'has_previous': offset > 0
            },
            'summary': {
                'total_amount': str(summary_stats['total_amount'] or 0),
                'average_amount': str(summary_stats['average_amount'] or 0),
                'total_fees': str(summary_stats['total_fees'] or 0),
                'status_breakdown': status_breakdown
            }
        }

        logger.info(f"Admin {user.username} retrieved {len(payouts_data)} payouts")
        return Response(response_data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response({
            'error': 'USER_NOT_FOUND',
            'detail': 'User not found in database.'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error in admin_list_all_payouts: {str(e)}", exc_info=True)
        return Response({
            'error': 'ADMIN_PAYOUTS_LIST_ERROR',
            'detail': f'Failed to retrieve payouts: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated, AdminRequired])
@financial_transaction
def admin_list_all_transactions(request):
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
        # Re-fetch the admin from the database for logging/auditing.
        user = User.objects.get(id=request.user.id)
        logger.info(f"Admin {user.username} accessing all transactions list")

        # Start with all transactions
        transactions = PaymentTransaction.objects.select_related(
            'seller', 'buyer', 'order'
        ).all()

        # Apply filters
        transaction_status = request.GET.get('status')
        if transaction_status:
            transactions = transactions.filter(status=transaction_status)

        seller_id = request.GET.get('seller_id')
        if seller_id:
            transactions = transactions.filter(seller_id=seller_id)

        buyer_id = request.GET.get('buyer_id')
        if buyer_id:
            transactions = transactions.filter(buyer_id=buyer_id)

        from_date = request.GET.get('from_date')
        if from_date:
            transactions = transactions.filter(created_at__gte=from_date)

        to_date = request.GET.get('to_date')
        if to_date:
            transactions = transactions.filter(created_at__lte=to_date)

        search = request.GET.get('search')
        if search:
            transactions = transactions.filter(
                Q(seller__username__icontains=search) |
                Q(buyer__username__icontains=search) |
                Q(order__id__icontains=search) |
                Q(stripe_payment_intent_id__icontains=search)
            )

        # Order by most recent first
        transactions = transactions.order_by('-created_at')

        # Pagination
        page_size = min(int(request.GET.get('page_size', 50)), 200)
        offset = int(request.GET.get('offset', 0))

        total_count = transactions.count()
        transactions_page = transactions[offset:offset + page_size]

        # Serialize transactions
        transactions_data = []
        for transaction in transactions_page:
            transaction_dict = {
                'id': str(transaction.id),
                'order_id': str(transaction.order.id) if transaction.order else None,
                'stripe_payment_intent_id': transaction.stripe_payment_intent_id,
                'status': transaction.status,
                'seller': {
                    'id': str(transaction.seller.id),
                    'username': transaction.seller.username,
                    'email': transaction.seller.email,
                },
                'buyer': {
                    'id': str(transaction.buyer.id),
                    'username': transaction.buyer.username,
                    'email': transaction.buyer.email,
                } if transaction.buyer else None,
                'amounts': {
                    'gross_amount': str(transaction.gross_amount),
                    'platform_fee': str(transaction.platform_fee),
                    'stripe_fee': str(transaction.stripe_fee),
                    'net_amount': str(transaction.net_amount),
                    'currency': transaction.currency,
                },
                'hold_info': {
                    'status': transaction.status,
                    'hold_reason': transaction.hold_reason,
                    'days_to_hold': transaction.days_to_hold,
                    'hold_start_date': transaction.hold_start_date.isoformat() if transaction.hold_start_date else None,
                    'planned_release_date': transaction.planned_release_date.isoformat() if transaction.planned_release_date else None,
                    'actual_release_date': transaction.actual_release_date.isoformat() if transaction.actual_release_date else None,
                },
                'payout_info': {
                    'payed_out': transaction.payed_out,
                },
                'timestamps': {
                    'created_at': transaction.created_at.isoformat(),
                    'updated_at': transaction.updated_at.isoformat(),
                    'purchase_date': transaction.purchase_date.isoformat() if transaction.purchase_date else None,
                }
            }
            transactions_data.append(transaction_dict)

        # Calculate summary statistics
        summary_stats = transactions.aggregate(
            total_gross=Sum('gross_amount'),
            total_net=Sum('net_amount'),
            total_platform_fees=Sum('platform_fee'),
            total_stripe_fees=Sum('stripe_fee'),
            average_transaction=Avg('gross_amount')
        )

        status_breakdown = {}
        for status_choice in ['held', 'completed', 'released', 'failed', 'refunded']:
            count = transactions.filter(status=status_choice).count()
            status_breakdown[status_choice] = count

        response_data = {
            'transactions': transactions_data,
            'pagination': {
                'total_count': total_count,
                'offset': offset,
                'page_size': page_size,
                'has_next': (offset + page_size) < total_count,
                'has_previous': offset > 0
            },
            'summary': {
                'total_gross': str(summary_stats['total_gross'] or 0),
                'total_net': str(summary_stats['total_net'] or 0),
                'total_platform_fees': str(summary_stats['total_platform_fees'] or 0),
                'total_stripe_fees': str(summary_stats['total_stripe_fees'] or 0),
                'average_transaction': str(summary_stats['average_transaction'] or 0),
                'status_breakdown': status_breakdown
            }
        }

        logger.info(f"Admin {user.username} retrieved {len(transactions_data)} transactions")
        return Response(response_data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response({
            'error': 'USER_NOT_FOUND',
            'detail': 'User not found in database.'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error in admin_list_all_transactions: {str(e)}", exc_info=True)
        return Response({
            'error': 'ADMIN_TRANSACTIONS_LIST_ERROR',
            'detail': f'Failed to retrieve transactions: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)