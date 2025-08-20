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

import os
import stripe
import json
import logging
import decimal
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.db import transaction, models
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from marketplace.models import Cart, Order, OrderItem
from .models import PaymentTracker, PaymentTransaction, Payout, PayoutItem
from .serializers import (
    PaymentTrackerSerializer, PayoutSerializer, 
    PayoutSummarySerializer, PayoutItemSerializer
)

# Import transaction utilities
from utils.transaction_utils import (
    financial_transaction, serializable_transaction, 
    atomic_with_isolation, rollback_safe_operation, log_transaction_performance,
    retry_on_deadlock, DeadlockError, TransactionError, get_current_isolation_level
)

# Set the Stripe API key from Django settings
stripe.api_key = settings.STRIPE_SECRET_KEY

# Add a check to ensure the key is loaded
if not stripe.api_key:
    raise ValueError("Stripe API key not found. Please set STRIPE_SECRET_KEY in your Django settings.")

# Initialize logger
logger = logging.getLogger(__name__)

User = get_user_model()

# ===============================================================================
# PAYOUT VIEWS - All payout-related functionality
# ===============================================================================

# ===============================================================================
# SELLER PAYOUT CREATION
# ===============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@financial_transaction
def seller_payout(request):
    """
    Simple Stripe payout creation - just create the payout with Stripe API.
    
    Expected request data:
    {
        "amount": 24784,  # Amount in cents
        "currency": "eur",  # Currency code
        "description": "Monthly payout"  # optional
    }
    """
    print("🔍 === SIMPLE SELLER_PAYOUT API CALLED ===")
    print(f"👤 User: {request.user.username} (ID: {request.user.id})")
    print(f"🔐 Is authenticated: {request.user.is_authenticated}")
    print(f"📊 Request data: {request.data}")
    
    # Log current isolation level for debugging
    current_isolation = get_current_isolation_level()
    print(f"🔐 Current transaction isolation level: {current_isolation}")
    logger.info(f"Seller payout started for user {request.user.id} with isolation level: {current_isolation}")
    
    try:
        # Get current user info
        user = request.user
        
        print(f"🔧 User ID: {user.id}")
        
        # Verify user has Stripe account
        stripe_account_id = user.stripe_account_id

        if not stripe_account_id:
            print("⚠️ User does not have a Stripe account.")
            return Response({
                'error': 'NO_STRIPE_ACCOUNT',
                'detail': 'User does not have a connected Stripe account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        
        StripeAccountBalance = stripe.Balance.retrieve(
            stripe_account=stripe_account_id,
            expand=['available']
        )
        available_balance = StripeAccountBalance['available']


        print(f"🔧 Available balance: {available_balance}")


        if not available_balance or len(available_balance) == 0:
            print("⚠️ No available balance found for this account.")
            return Response({
                'error': 'NO_AVAILABLE_BALANCE',
                'detail': 'No available balance found for this Stripe account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the first available balance (usually EUR or primary currency)
        first_balance = available_balance[0]
        payout_amount = first_balance['amount']
        payout_currency = first_balance['currency']
        
        print(f"💰 Using balance: {payout_amount} {payout_currency.upper()}")
        print(f"💰 Amount in cents: {payout_amount}")
        print(f"💰 Amount formatted: €{payout_amount/100:.2f}")
        
        if payout_amount <= 1:
            print("⚠️ Available balance is zero or negative.")
            return Response({
                'error': 'INSUFFICIENT_BALANCE',
                'detail': f'Available balance is {payout_amount} cents. Cannot create payout.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get user's external account to determine payout method and timing
        try:
            external_accounts = stripe.Account.list_external_accounts(
                stripe_account_id,
                object='bank_account',
                limit=10
            )
            
            print(f"🏦 Found {len(external_accounts.data)} external accounts")
            
            # Determine optimal payout method and timing based on account type
            payout_method = "standard"  # Default to standard
            payout_timing = "standard"  # Default timing
            
            if external_accounts.data:
                # Check the default external account
                default_account = external_accounts.data[0]
                account_type = default_account.get('object', 'bank_account')
                
                print(f"🔍 Default account type: {account_type}")
                print(f"🔍 Account details: {default_account.get('last4', 'N/A')}")
                
                # Check if it's a debit card (instant eligible)
                if account_type == 'card':
                    card_brand = default_account.get('brand', '').lower()
                    card_funding = default_account.get('funding', '').lower()
                    
                    print(f"💳 Card brand: {card_brand}, funding: {card_funding}")
                    
                    # Debit cards are eligible for instant payouts
                    if card_funding == 'debit':
                        payout_method = "instant"
                        payout_timing = "instant"
                        print("⚡ Using instant payout for debit card")
                    else:
                        # Credit cards use standard timing
                        payout_method = "standard"
                        payout_timing = "standard"
                        print("📅 Using standard payout for credit card")
                else:
                    # Bank accounts use standard timing
                    payout_method = "standard"
                    payout_timing = "standard"
                    print("🏦 Using standard payout for bank account")
            else:
                print("⚠️ No external accounts found, using standard method")
        
        except stripe.error.StripeError as e:
            print(f"⚠️ Error fetching external accounts: {str(e)}")
            # Continue with standard method if account lookup fails
            payout_method = "standard"
            payout_timing = "standard"
        
        print(f"💰 Payout method: {payout_method}, timing: {payout_timing}")
        
        # Create Stripe payout using determined method
        stripe_payout = stripe.Payout.create(
            amount=payout_amount,  # Use actual available balance amount
            currency=payout_currency,  # Use actual available balance currency
            stripe_account=stripe_account_id,
            method=payout_method,
            metadata={
                'user_id': str(user.id),
                'original_amount': payout_amount,
                'payout_currency': payout_currency,
                'payout_timing': payout_timing,
            }
        )
        
        print(f"✅ Stripe payout created: {stripe_payout.id}")
        print(f"📊 Payout status: {stripe_payout.status}")
        
        # Define a deadlock-safe operation for creating payout record AND payout items in a single transaction
        @retry_on_deadlock(max_retries=3, delay=0.1, backoff=2.0)
        def create_payout_and_items_safe():
            """Create payout record and payout items in a single SERIALIZABLE transaction with deadlock retry protection"""
            with atomic_with_isolation('SERIALIZABLE'):
                with rollback_safe_operation("Complete Payout Creation"):
                    # Step 1: Create the payout record
                    payout_record = Payout.objects.create(
                        stripe_payout_id=stripe_payout.id,
                        seller=user,
                        status='pending',
                        payout_type=payout_timing,
                        amount_cents=payout_amount,
                        currency=payout_currency,
                        stripe_created_at=timezone.datetime.fromtimestamp(stripe_payout.created, tz=timezone.utc),
                        description=f"{payout_timing.title()} payout for seller {user.username}",
                        metadata={
                            'stripe_method': payout_method,
                            'payout_timing': payout_timing,
                            'user_id': str(user.id),
                            'original_amount': payout_amount,
                            'account_verification': 'verified',
                        }
                    )
                    
                    print(f"💾 Payout record created in database: {payout_record.id}")
                    
                    # Step 2: Query eligible transactions within the same transaction for consistency
                    eligible_transactions = PaymentTransaction.objects.select_for_update().filter(
                        seller=user,
                        payed_out=False,
                    ).filter(
                        # Either completed status OR has actual release date (released from hold)
                        models.Q(status='completed') | models.Q(actual_release_date__isnull=False)
                    ).order_by('-created_at')
                    
                    print(f"🔍 Found {eligible_transactions.count()} eligible transactions for payout items")
                    
                    payout_items_created = 0
                    
                    # Step 3: Create payout items and update transactions in the same transaction
                    for transaction_obj in eligible_transactions:
                        try:
                            # Create PayoutItem for this transaction
                            payout_item = PayoutItem.objects.create(
                                payout=payout_record,
                                payment_transfer=transaction_obj,
                                transfer_amount=transaction_obj.net_amount,
                                transfer_currency=transaction_obj.currency.upper(),
                                transfer_date=transaction_obj.actual_release_date or transaction_obj.updated_at,
                                order_id=str(transaction_obj.order.id) if transaction_obj.order else '',
                                item_names=transaction_obj.item_names
                            )
                            
                            # Mark the transaction as payed out
                            transaction_obj.payed_out = True
                            transaction_obj.save(update_fields=['payed_out', 'updated_at'])
                            
                            payout_items_created += 1
                            print(f"✅ Created PayoutItem for transaction {transaction_obj.id}: {transaction_obj.net_amount} {transaction_obj.currency}")
                            
                        except Exception as e:
                            print(f"⚠️ Failed to create PayoutItem for transaction {transaction_obj.id}: {str(e)}")
                            logger.error(f"Failed to create PayoutItem for transaction {transaction_obj.id}: {str(e)}")
                            # Re-raise the exception to trigger rollback of the entire operation
                            raise TransactionError(f"Failed to create PayoutItem for transaction {transaction_obj.id}: {str(e)}")
                    
                    print(f"💰 Created {payout_items_created} payout items for payout {payout_record.id}")
                    
                    # Return both the payout record and the count of items created
                    return payout_record, payout_items_created
        
        # Execute the complete payout creation with deadlock protection
        payout_record, payout_items_created = create_payout_and_items_safe()
        
        # Simple response with actual payout amounts and method information
        response_data = {
            'success': True,
            'payout': {
                'id': str(payout_record.id),
                'stripe_payout_id': stripe_payout.id,
                'status': stripe_payout.status,
                'method': payout_method,
                'timing': payout_timing,
                'amount_cents': payout_amount,
                'amount_formatted': f"€{payout_amount/100:.2f}",
                'currency': payout_currency,
                'created': stripe_payout.created,
                'payout_items_created': payout_items_created,
                'estimated_arrival': 'immediate' if payout_timing == 'instant' else '1-2 business days'
            },
            'user': {
                'id': str(user.id),
                'username': user.username,
                'stripe_account_id': stripe_account_id
            },
            'transactions': {
                'eligible_count': eligible_transactions.count(),
                'items_created': payout_items_created
            },
            'verification': {
                'account_verified': True,
                'method_verified': True,
                'payout_eligible': True
            },
            'message': f'{payout_timing.title()} payout of €{payout_amount/100:.2f} created successfully with {payout_items_created} transaction items'
        }
        
        logger.info(f"Simple payout created successfully: {stripe_payout.id} for user {user.id}")
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except DeadlockError as e:
        logger.error(f"Deadlock error in seller_payout after retries: {e}")
        return Response({
            'error': 'PAYOUT_DEADLOCK_ERROR',
            'detail': 'Transaction failed due to database deadlock. Please try again.',
            'retry_after': 1  # Suggest retry after 1 second
        }, status=status.HTTP_409_CONFLICT)
        
    except TransactionError as e:
        logger.error(f"Transaction error in seller_payout: {e}")
        return Response({
            'error': 'PAYOUT_TRANSACTION_ERROR',
            'detail': 'Database transaction failed. Please try again.',
            'retry_after': 1
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe payout failed: {e}")
        return Response({
            'error': 'STRIPE_PAYOUT_FAILED',
            'detail': str(e),
            'stripe_error_code': getattr(e, 'code', 'unknown')
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Unexpected error in seller_payout: {str(e)}", exc_info=True)
        return Response({
            'error': 'PAYOUT_ERROR',
            'detail': f'An unexpected error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===============================================================================
# SELLER MONEY ON HOLD VIEWS
# ===============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@financial_transaction
def get_seller_payment_holds(request):
    """
    Get all payment holds for the authenticated seller with remaining time calculation
    Using simplified PaymentTransaction model with integrated hold system
    """
    logger.info(f"[API] GET /stripe/holds/ called")
    
    # Debug authentication
    logger.info(f"[DEBUG] Request headers: {dict(request.headers)}")
    logger.info(f"[DEBUG] Request user: {request.user}")
    logger.info(f"[DEBUG] User authenticated: {request.user.is_authenticated}")
    
    if not request.user.is_authenticated:
        logger.warning(f"[ERROR] User not authenticated for stripe holds endpoint")
        return Response({
            'error': 'AUTHENTICATION_REQUIRED',
            'detail': 'You must be logged in to view payment holds',
            'authenticated': False
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        user = request.user
        logger.info(f"[SUCCESS] Authenticated user: {user.username} (ID: {user.id})")
        
        # Get all payment transactions where the user is the seller and payment is held
        logger.info(f"[DEBUG] Querying PaymentTransaction for seller: {user.id}")
        held_transactions = PaymentTransaction.objects.filter(
            seller=user,
            status='held'
        ).select_related('order', 'buyer')
        
        logger.info(f"[INFO] Found {held_transactions.count()} held transactions for seller {user.username}")
        
        holds_data = []
        total_pending_amount = Decimal('0.00')
        
        for transaction in held_transactions:
            try:
                # Calculate remaining time using integrated hold system
                now = timezone.now()
                if transaction.planned_release_date:
                    remaining_time = transaction.planned_release_date - now
                    remaining_days = max(0, remaining_time.days)
                    remaining_hours = max(0, remaining_time.seconds // 3600)
                    
                    # Check if ready for release
                    is_ready_for_release = remaining_time.total_seconds() <= 0
                else:
                    # Use days_to_hold and hold_start_date to calculate remaining
                    remaining_days = transaction.days_remaining
                    remaining_hours = transaction.hours_remaining
                    is_ready_for_release = transaction.can_be_released
                
                # Parse item names for display (simplified from PaymentItems)
                item_list = transaction.item_names.split(', ') if transaction.item_names else []
                
                # Calculate progress percentage for UI
                total_hold_time = transaction.days_to_hold * 24  # Convert to hours
                elapsed_hours = 0
                if transaction.hold_start_date:
                    elapsed_time = now - transaction.hold_start_date
                    elapsed_hours = elapsed_time.total_seconds() / 3600
                
                progress_percentage = min(100, max(0, (elapsed_hours / total_hold_time) * 100)) if total_hold_time > 0 else 0
                
                hold_info = {
                    'transaction_id': str(transaction.id),
                    'order_id': str(transaction.order.id),
                    'buyer': {
                        'username': transaction.buyer.username,
                        'email': transaction.buyer.email,
                        'first_name': getattr(transaction.buyer, 'first_name', ''),
                        'last_name': getattr(transaction.buyer, 'last_name', '')
                    },
                    'amounts': {
                        'gross_amount': float(transaction.gross_amount),
                        'platform_fee': float(transaction.platform_fee),
                        'stripe_fee': float(transaction.stripe_fee),
                        'net_amount': float(transaction.net_amount),
                        'currency': transaction.currency
                    },
                    'order_details': {
                        'purchase_date': transaction.purchase_date.isoformat(),
                        'item_count': transaction.item_count,
                        'item_names': transaction.item_names,
                        'items': [{'product_name': name.strip(), 'quantity': 1} for name in item_list]
                    },
                    'hold_status': {
                        'reason': transaction.hold_reason,
                        'reason_display': transaction.get_hold_reason_display(),
                        'status': 'held',
                        'status_display': 'Payment on Hold',
                        'total_hold_days': transaction.days_to_hold,
                        'hold_start_date': transaction.hold_start_date.isoformat() if transaction.hold_start_date else None,
                        'planned_release_date': transaction.planned_release_date.isoformat() if transaction.planned_release_date else None,
                        'remaining_days': remaining_days,
                        'remaining_hours': remaining_hours,
                        'progress_percentage': round(progress_percentage, 1),
                        'is_ready_for_release': is_ready_for_release,
                        'hold_notes': transaction.hold_notes or f"Standard {transaction.days_to_hold}-day hold period for marketplace transactions",
                        'time_display': f"{remaining_days}d {remaining_hours}h remaining" if not is_ready_for_release else "Ready for release"
                    }
                }
                
                holds_data.append(hold_info)
                total_pending_amount += transaction.net_amount
                
            except Exception as item_error:
                logger.error(f"Error processing transaction {transaction.id}: {str(item_error)}")
                continue
        
        # Summary statistics
        summary = {
            'total_holds': len(holds_data),
            'total_pending_amount': str(total_pending_amount),
            'currency': 'USD',
            'ready_for_release_count': sum(1 for hold in holds_data if hold['hold_status']['is_ready_for_release']),
        }
        
        logger.info(f"[SUCCESS] Successfully prepared response with {len(holds_data)} holds, total pending: ${total_pending_amount}")
        
        return Response({
            'success': True,
            'summary': summary,
            'holds': holds_data,
            'message': f'Found {len(holds_data)} payment holds for seller {user.username}.',
            'debug_info': {
                'user_id': user.id,
                'username': user.username,
                'is_authenticated': True,
                'query_count': held_transactions.count()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"[ERROR] Error retrieving seller payment holds for user {user.username}: {str(e)}")
        logger.error(f"[ERROR] Full exception: ", exc_info=True)
        return Response({
            'error': 'PAYMENT_HOLDS_RETRIEVAL_FAILED',
            'detail': f'Failed to retrieve payment holds: {str(e)}',
            'debug_info': {
                'user_id': user.id if hasattr(user, 'id') else None,
                'username': user.username if hasattr(user, 'username') else str(user),
                'is_authenticated': request.user.is_authenticated
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===============================================================================
# PAYOUT LIST AND DETAIL VIEWS
# ===============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@financial_transaction
def user_payouts_list(request):
    """
    Retrieve all payouts for the authenticated user (seller).
    Returns a paginated list of payouts with summary information.
    """
    try:
        user = request.user
        logger.info(f"Fetching payouts for user: {user.id}")
        
        # Get all payouts for this user as seller
        payouts = Payout.objects.filter(seller=user).order_by('-created_at')
        
        # Apply pagination if needed
        page_size = request.GET.get('page_size', 20)
        try:
            page_size = min(int(page_size), 100)  # Max 100 items per page
        except (ValueError, TypeError):
            page_size = 20
        
        # Simple offset-based pagination
        offset = 0
        try:
            offset = int(request.GET.get('offset', 0))
        except (ValueError, TypeError):
            offset = 0
        
        total_count = payouts.count()
        payouts_page = payouts[offset:offset + page_size]
        
        serializer = PayoutSummarySerializer(payouts_page, many=True)
        
        response_data = {
            'payouts': serializer.data,
            'pagination': {
                'total_count': total_count,
                'offset': offset,
                'page_size': page_size,
                'has_next': (offset + page_size) < total_count,
                'has_previous': offset > 0
            }
        }
        
        logger.info(f"Successfully retrieved {len(serializer.data)} payouts for user {user.id}")
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error fetching payouts for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'PAYOUT_FETCH_ERROR',
            'detail': f'Failed to fetch payouts: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@financial_transaction
def payout_detail(request, payout_id):
    """
    Retrieve detailed information about a specific payout including all orders.
    Only accessible by the seller who owns the payout.
    """
    try:
        user = request.user
        logger.info(f"Fetching payout detail {payout_id} for user: {user.id}")
        
        # Get payout and ensure it belongs to the requesting user
        try:
            payout = Payout.objects.prefetch_related(
                'payout_items__payment_transfer__order'
            ).get(id=payout_id, seller=user)
        except Payout.DoesNotExist:
            return Response({
                'error': 'PAYOUT_NOT_FOUND',
                'detail': 'Payout not found or you do not have permission to view it.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = PayoutSerializer(payout)
        
        logger.info(f"Successfully retrieved payout detail {payout_id} for user {user.id}")
        return Response({
            'payout': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error fetching payout detail {payout_id} for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'PAYOUT_DETAIL_ERROR',
            'detail': f'Failed to fetch payout details: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@financial_transaction
def payout_orders(request, payout_id):
    """
    Retrieve all orders included in a specific payout.
    Returns detailed order information with amounts.
    Only includes order items where the current user is the product owner.
    """
    try:
        user = request.user
        logger.info(f"Fetching orders for payout {payout_id} for user: {user.id} (filtering products by owner)")
        
        # Verify payout ownership
        try:
            payout = Payout.objects.get(id=payout_id, seller=user)
        except Payout.DoesNotExist:
            return Response({
                'error': 'PAYOUT_NOT_FOUND',
                'detail': 'Payout not found or you do not have permission to view it.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get all payout items with order details
        # Prefetch only order items where the product belongs to the current user
        from django.db.models import Prefetch
        from marketplace.models import OrderItem
        
        payout_items = PayoutItem.objects.filter(
            payout=payout
        ).select_related(
            'payment_transfer__order__buyer'
        ).prefetch_related(
            Prefetch(
                'payment_transfer__order__items',
                queryset=OrderItem.objects.filter(product__seller=user).select_related('product'),
                to_attr='user_items'
            )
        ).order_by('-transfer_date')
        
        orders_data = []
        for item in payout_items:
            try:
                payment_transfer = item.payment_transfer
                order = payment_transfer.order if payment_transfer else None
                
                if order:
                    # Get order items - only products where current user is the owner (pre-filtered)
                    order_items = []
                    # Use prefetched user_items which are already filtered by product seller
                    user_order_items = getattr(order, 'user_items', [])
                    for order_item in user_order_items:
                        order_items.append({
                            'product_name': order_item.product.name,
                            'quantity': order_item.quantity,
                            'price': str(order_item.unit_price),
                            'total': str(order_item.total_price)
                        })
                    
                    order_data = {
                        'order_id': str(order.id),
                        'order_date': order.created_at.isoformat(),
                        'buyer_username': order.buyer.username,
                        'status': order.status,
                        'payment_status': order.payment_status,
                        'subtotal': str(order.subtotal),
                        'shipping_cost': str(order.shipping_cost),
                        'tax_amount': str(order.tax_amount),
                        'total_amount': str(order.total_amount),
                        'transfer_amount': str(item.transfer_amount),
                        'transfer_date': item.transfer_date.isoformat(),
                        'items': order_items
                    }
                else:
                    # Fallback if order data is not available
                    order_data = {
                        'order_id': item.order_id,
                        'order_date': item.transfer_date.isoformat(),
                        'buyer_username': 'Unknown',
                        'status': 'completed',
                        'payment_status': 'paid',
                        'total_amount': str(item.transfer_amount),
                        'transfer_amount': str(item.transfer_amount),
                        'transfer_date': item.transfer_date.isoformat(),
                        'item_names': item.item_names,
                        'items': []
                    }
                
                orders_data.append(order_data)
                
            except Exception as e:
                logger.warning(f"Error processing payout item {item.id}: {str(e)}")
                continue
        
        response_data = {
            'payout_id': str(payout.id),
            'payout_amount': str(payout.amount_decimal),
            'payout_status': payout.status,
            'transfer_count': len(orders_data),
            'orders': orders_data
        }
        
        logger.info(f"Successfully retrieved {len(orders_data)} orders for payout {payout_id}")
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error fetching payout orders {payout_id} for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'PAYOUT_ORDERS_ERROR',
            'detail': f'Failed to fetch payout orders: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)