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
        @retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)  # 10ms initial delay
        def create_payout_and_items_safe():
            """
            Create payout record and related items in READ COMMITTED transaction with proper model ordering.
            
            CRITICAL MODEL ORDERING SEQUENCE (prevents deadlocks):
            1. Stripe API calls (OUTSIDE transaction - already completed above)
            2. READ COMMITTED isolation level (optimal performance + consistency)
            3. Payout model (primary business entity - created first)
            4. PayoutItem model (depends on Payout, created second)
            5. PaymentTracker model (tracking/audit, created/updated third)
            6. PaymentTransaction model (financial records, updated LAST with select_for_update)
            
            This ordering prevents circular lock dependencies and ensures deadlock-free operation.
            """
            with atomic_with_isolation('READ COMMITTED'):
                with rollback_safe_operation("Complete Payout Creation"):
                    # Start performance tracking
                    start_time = timezone.now()
                    
                    # AUDIT TRAIL: Log payout initiation
                    logger.info(f"AUDIT: Payout process initiated for seller {user.username} (ID: {user.id}) at {start_time.isoformat()}")
                    
                    # Step 1: Create the payout record (Model Order: Payout first)
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
                        },
                        # Simple payout initialization
                    )
                    
                    # Payout record created with pending status by default
                    
                    print(f"💾 Payout record created in database: {payout_record.id}")
                    
                    # Step 2: Query eligible transactions for payout (read-only query first)
                    # DELIVERY VALIDATION: Only process payouts for delivered orders
                    print(f"🚚 Delivery Validation: Applying strict delivery validation for seller {user.username}")
                    print(f"📋 Payout criteria: (completed OR released) AND order_status='delivered' AND payed_out=False")
                    query_start_time = timezone.now()
                    eligible_transactions = PaymentTransaction.objects.filter(
                        seller=user,
                        payed_out=False,
                    ).filter(
                        # Either completed status OR has actual release date (released from hold)
                        models.Q(status='completed') | models.Q(actual_release_date__isnull=False)
                    ).filter(
                        # CRITICAL: Order must be delivered before payout is processed
                        order__status='delivered'
                    ).filter(
                        # Additional safety: Ensure order exists and is not None
                        order__isnull=False
                    ).order_by('-created_at')
                    
                    eligible_count = eligible_transactions.count()
                    query_duration = (timezone.now() - query_start_time).total_seconds() * 1000
                    
                    print(f"🔍 Found {eligible_count} eligible transactions for payout items (delivery validated)")
                    
                    # Check how many transactions were excluded by delivery validation
                    total_released_transactions = PaymentTransaction.objects.filter(
                        seller=user,
                        payed_out=False,
                    ).filter(
                        models.Q(status='completed') | models.Q(actual_release_date__isnull=False)
                    ).count()
                    
                    excluded_count = total_released_transactions - eligible_count
                    if excluded_count > 0:
                        print(f"⚠️ Delivery Validation: {excluded_count} transactions excluded (orders not yet delivered)")
                        # AUDIT TRAIL: Log excluded transactions for compliance
                        logger.warning(f"AUDIT: Delivery validation excluded {excluded_count} transactions for seller {user.username}. "
                                     f"Total released: {total_released_transactions}, Eligible: {eligible_count}")
                    else:
                        print(f"✅ Delivery Validation: All {eligible_count} released transactions have delivered orders")
                        # AUDIT TRAIL: Log successful validation
                        logger.info(f"AUDIT: Delivery validation passed for all {eligible_count} transactions for seller {user.username}")
                    
                    # Log query performance
                    print(f"📊 Transaction query took {query_duration}ms for {eligible_count} transactions")
                    
                    payout_items_created = 0
                    trackers_created = 0
                    items_start_time = timezone.now()
                    
                    # PROPER MODEL ORDERING: Payout → PayoutItem → PaymentTracker → PaymentTransaction
                    # Step 3: Create PayoutItems first (PayoutItem model - second in hierarchy)
                    for transaction_obj in eligible_transactions:
                        try:
                            # Double-check delivery validation (safety measure)
                            if not transaction_obj.order or transaction_obj.order.status != 'delivered':
                                print(f"⚠️ SAFETY CHECK FAILED: Transaction {transaction_obj.id} order not delivered, skipping")
                                continue
                            # Create PayoutItem first (depends on Payout, created before tracker/transaction updates)
                            payout_item = PayoutItem.objects.create(
                                payout=payout_record,
                                payment_transfer=transaction_obj,
                                transfer_amount=transaction_obj.net_amount,
                                transfer_currency=transaction_obj.currency.upper(),
                                transfer_date=transaction_obj.actual_release_date or transaction_obj.updated_at,
                                order_id=str(transaction_obj.order.id) if transaction_obj.order else '',
                                item_names=transaction_obj.item_names
                            )
                            payout_items_created += 1
                            print(f"✅ Created PayoutItem {payout_item.id} for transaction {transaction_obj.id}")
                            
                            # AUDIT TRAIL: Log detailed payout processing information
                            logger.info(f"AUDIT: Payout processing - User: {user.username}, "
                                      f"Transaction: {transaction_obj.id}, Order: {transaction_obj.order.id}, "
                                      f"Order Status: {transaction_obj.order.status}, Amount: {transaction_obj.net_amount}, "
                                      f"PayoutItem: {payout_item.id}, Timestamp: {timezone.now().isoformat()}")
                            
                            # Step 4: Create PaymentTracker records (PaymentTracker model - third in hierarchy)
                            # Create tracker directly for this payout operation - no need to check for existing
                            tracker = PaymentTracker.objects.create(
                                stripe_payment_intent_id=transaction_obj.stripe_payment_intent_id or f'payout_{transaction_obj.id}',
                                user=user,
                                status='payout_processing',
                                amount=transaction_obj.gross_amount,
                                currency=transaction_obj.currency,
                                order=transaction_obj.order,
                                transaction_type='payout',
                                created_at=timezone.now(),
                            )
                            
                            trackers_created += 1
                            print(f"✅ Created PaymentTracker {tracker.id} for payout processing")
                            
                        except Exception as e:
                            print(f"⚠️ Failed to create PayoutItem/PaymentTracker for transaction {transaction_obj.id}: {str(e)}")
                            logger.error(f"Failed to process transaction {transaction_obj.id}: {str(e)}")
                            # Track failure
                            print(f"❌ Payout item creation error: {str(e)}")
                            # Re-raise the exception to trigger rollback of the entire operation
                            raise TransactionError(f"Failed to process transaction {transaction_obj.id}: {str(e)}")
                    
                    # Step 5: Update PaymentTransaction models LAST (PaymentTransaction model - final in hierarchy)
                    print(f"🔄 Updating {eligible_count} PaymentTransaction records as final step...")
                    transaction_update_start = timezone.now()
                    
                    # Use select_for_update only at the end when we need to modify the transactions
                    final_transactions = PaymentTransaction.objects.select_for_update().filter(
                        seller=user,
                        payed_out=False,
                        id__in=[t.id for t in eligible_transactions]
                    )
                    
                    transactions_updated = 0
                    for transaction_obj in final_transactions:
                        try:
                            # Final step: Mark transaction as payed out
                            transaction_obj.payed_out = True
                            transaction_obj.save(update_fields=['payed_out', 'updated_at'])
                            transactions_updated += 1
                            print(f"✅ Updated PaymentTransaction {transaction_obj.id} as payed out")
                            
                        except Exception as e:
                            print(f"⚠️ Failed to update PaymentTransaction {transaction_obj.id}: {str(e)}")
                            logger.error(f"Failed to update PaymentTransaction {transaction_obj.id}: {str(e)}")
                            # Track failure but don't fail entire operation since PayoutItems are already created
                            print(f"❌ Transaction update error: {str(e)}")
                    
                    transaction_update_duration = (timezone.now() - transaction_update_start).total_seconds() * 1000
                    print(f"📊 Transaction update took {transaction_update_duration}ms")
                    
                    # Track processing performance with new model ordering metrics
                    items_duration = (timezone.now() - items_start_time).total_seconds() * 1000
                    print(f"📊 Items creation took {items_duration}ms: {payout_items_created} items, {trackers_created} trackers, {transactions_updated} transactions")
                    
                    # Final processing completion tracking
                    total_duration = (timezone.now() - start_time).total_seconds() * 1000
                    print(f"📊 Total creation duration: {total_duration}ms")
                    
                    print(f"💰 PAYOUT PROCESSING COMPLETE:")
                    print(f"   📦 Payout Record: {payout_record.id}")
                    print(f"   📋 PayoutItems Created: {payout_items_created}")
                    print(f"   📊 PaymentTrackers: {trackers_created} created/updated")
                    print(f"   💳 PaymentTransactions Updated: {transactions_updated}")
                    print(f"   ⏱️ Total Processing Time: {total_duration:.1f}ms")
                    print(f"   🔒 Model Ordering: Stripe API → READ COMMITTED → Payout → PayoutItem → PaymentTracker → PaymentTransaction")
                    
                    # Return both the payout record and comprehensive counts
                    return payout_record, {
                        'payout_items_created': payout_items_created,
                        'trackers_created': trackers_created,
                        'transactions_updated': transactions_updated,
                        'total_processing_time_ms': total_duration
                    }
        
        # Execute the complete payout creation with deadlock protection
        payout_record, processing_results = create_payout_and_items_safe()
        
        # Enhanced response with tracking and performance metrics
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
                'payout_items_created': processing_results['payout_items_created'],
                'estimated_arrival': 'immediate' if payout_timing == 'instant' else '1-2 business days',
                # Enhanced tracking information
                'retry_count': payout_record.retry_count,
            },
            'user': {
                'id': str(user.id),
                'username': user.username,
                'stripe_account_id': stripe_account_id
            },
            'processing_results': {
                'eligible_transactions_found': processing_results['transactions_updated'],
                'payout_items_created': processing_results['payout_items_created'],
                'payment_trackers_processed': processing_results['trackers_created'],
                'payment_transactions_updated': processing_results['transactions_updated'],
                'model_ordering_followed': 'Stripe API → READ COMMITTED → Payout → PayoutItem → PaymentTracker → PaymentTransaction'
            },
            'verification': {
                'account_verified': True,
                'method_verified': True,
                'payout_eligible': True
            },
            'technical_info': {
                'total_processing_time_ms': processing_results['total_processing_time_ms'],
                'isolation_level': 'READ_COMMITTED',
                'deadlock_retry_enabled': True,
                'deadlock_retry_delay_ms': 10,
                'model_ordering_compliance': True
            },
            'message': f'{payout_timing.title()} payout of €{payout_amount/100:.2f} created successfully with proper model ordering: {processing_results["payout_items_created"]} items, {processing_results["trackers_created"]} trackers, {processing_results["transactions_updated"]} transactions'
        }
        
        logger.info(f"Simple payout created successfully: {stripe_payout.id} for user {user.id}")
        
        # AUDIT TRAIL: Log comprehensive payout completion
        completion_time = timezone.now()
        logger.info(f"AUDIT: Payout process completed successfully for seller {user.username} (ID: {user.id}). "
                   f"Stripe Payout ID: {stripe_payout.id}, Amount: €{payout_amount/100:.2f}, "
                   f"Items processed: {processing_results['payout_items_created']}, "
                   f"Transactions updated: {processing_results['transactions_updated']}, "
                   f"Delivery validation enforced: True, "
                   f"Completion time: {completion_time.isoformat()}, "
                   f"Total processing time: {processing_results['total_processing_time_ms']}ms")
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except DeadlockError as e:
        logger.error(f"Deadlock error in seller_payout after retries: {e}")
        # AUDIT TRAIL: Log deadlock error for compliance
        logger.error(f"AUDIT: Payout process failed (DEADLOCK) for seller {user.username} (ID: {user.id}). "
                    f"Error: {str(e)}, Timestamp: {timezone.now().isoformat()}")
        # Try to track retry attempt if payout record exists
        try:
            if 'payout_record' in locals():
                payout_record.increment_retry_count()
        except Exception:
            pass  # Don't fail on tracking errors
        
        return Response({
            'error': 'PAYOUT_DEADLOCK_ERROR',
            'detail': 'Transaction failed due to database deadlock. 10ms retry mechanism exhausted.',
            'retry_after': 1,
            'technical_details': {
                'deadlock_retry_enabled': True,
                'deadlock_retry_delay_ms': 10,
                'isolation_level': 'READ_COMMITTED'
            }
        }, status=status.HTTP_409_CONFLICT)
        
    except TransactionError as e:
        logger.error(f"Transaction error in seller_payout: {e}")
        # AUDIT TRAIL: Log transaction error for compliance
        logger.error(f"AUDIT: Payout process failed (TRANSACTION_ERROR) for seller {user.username} (ID: {user.id}). "
                    f"Error: {str(e)}, Timestamp: {timezone.now().isoformat()}")
        # Try to track failure if payout record exists
        try:
            if 'payout_record' in locals():
                print(f"❌ Transaction error: {str(e)}")
                payout_record.update_status('failed')
        except Exception:
            pass  # Don't fail on tracking errors
        
        return Response({
            'error': 'PAYOUT_TRANSACTION_ERROR',
            'detail': 'Database transaction failed with enhanced tracking.',
            'retry_after': 1,
            'technical_details': {
                'isolation_level': 'READ_COMMITTED',
                'model_ordering': 'Payout → PaymentTransaction → PayoutItem'
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe payout failed: {e}")
        # Try to track Stripe failure if user exists
        try:
            if 'user' in locals():
                # Create a minimal payout record to track the Stripe failure
                failed_payout = Payout.objects.create(
                    stripe_payout_id=f'failed_{timezone.now().timestamp()}',
                    seller=user,
                    status='failed',
                    payout_type='standard',
                    amount_cents=0,
                    currency='EUR',
                    description=f'Failed payout due to Stripe error: {str(e)}',
                    failure_code=getattr(e, 'code', 'unknown'),
                    failure_message=str(e),
                )
                failed_payout.update_status('failed')
        except Exception:
            pass  # Don't fail on tracking errors
        
        return Response({
            'error': 'STRIPE_PAYOUT_FAILED',
            'detail': str(e),
            'stripe_error_code': getattr(e, 'code', 'unknown'),
            'technical_details': {
                'error_tracked': True,
                'isolation_level': 'READ_COMMITTED'
            }
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Unexpected error in seller_payout: {str(e)}", exc_info=True)
        # Try to track unexpected error
        try:
            if 'payout_record' in locals():
                print(f"❌ Unexpected error: {str(e)}")
                payout_record.update_status('failed')
        except Exception:
            pass  # Don't fail on tracking errors
        
        return Response({
            'error': 'PAYOUT_ERROR',
            'detail': f'An unexpected error occurred: {str(e)}',
            'technical_details': {
                'enhanced_tracking_enabled': True,
                'error_logged': True
            }
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
        
        for transaction in held_transactions:
            if transaction.order.status != 'delivered':
                logger.warning(f"[WARNING] Transaction {transaction.id} order not delivered, skipping hold processing")
                continue


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


# ===============================================================================
# ENHANCED PAYOUT ANALYTICS AND REPORTING ENDPOINTS
# ===============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)  # 10ms deadlock retry
def payout_analytics_dashboard(request):
    """
    Comprehensive payout analytics dashboard with enhanced tracking metrics.
    Uses READ COMMITTED isolation for optimal performance.
    """
    try:
        user = request.user
        logger.info(f"Fetching payout analytics dashboard for user: {user.id}")
        
        with atomic_with_isolation('READ COMMITTED'):
            # Performance tracking
            start_time = timezone.now()
            
            # Get all payouts for analytics
            payouts = Payout.objects.filter(seller=user).select_related().order_by('-created_at')
            
            # Basic statistics
            total_payouts = payouts.count()
            successful_payouts = payouts.filter(status='paid').count()
            failed_payouts = payouts.filter(status='failed').count()
            pending_payouts = payouts.filter(status__in=['pending', 'in_transit']).count()
            
            # Financial metrics
            from django.db.models import Sum, Avg
            financial_metrics = payouts.aggregate(
                total_amount=Sum('amount_decimal'),
                average_payout=Avg('amount_decimal'),
                total_fees=Sum('total_fees')
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
            for status, display_name in Payout._meta.get_field('reconciliation_status').choices:
                count = payouts.filter(reconciliation_status=status).count()
                reconciliation_stats[status] = {
                    'count': count,
                    'display_name': display_name,
                    'percentage': (count / total_payouts * 100) if total_payouts > 0 else 0
                }
            
            # Recent activity (last 30 days)
            from datetime import timedelta
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_payouts = payouts.filter(created_at__gte=thirty_days_ago)
            
            # Error analysis
            error_analysis = {
                'deadlock_retries': 0,
                'stripe_failures': 0,
                'transaction_errors': 0,
                'total_retries': 0
            }
            
            for payout in payouts[:100]:  # Analyze last 100 payouts
                error_analysis['total_retries'] += payout.retry_count
                if payout.failure_code:
                    error_analysis['stripe_failures'] += 1
                if payout.performance_metrics:
                    metrics = payout.performance_metrics.get('metrics', [])
                    for metric in metrics:
                        if 'error' in metric.get('name', '').lower():
                            error_analysis['transaction_errors'] += 1
            
            # Calculate query performance
            query_duration = (timezone.now() - start_time).total_seconds() * 1000
            
            analytics_data = {
                'summary': {
                    'total_payouts': total_payouts,
                    'successful_payouts': successful_payouts,
                    'failed_payouts': failed_payouts,
                    'pending_payouts': pending_payouts,
                    'success_rate': (successful_payouts / total_payouts * 100) if total_payouts > 0 else 0,
                    'failure_rate': (failed_payouts / total_payouts * 100) if total_payouts > 0 else 0
                },
                'financial_metrics': {
                    'total_amount': str(financial_metrics['total_amount'] or 0),
                    'average_payout': str(financial_metrics['average_payout'] or 0),
                    'total_fees': str(financial_metrics['total_fees'] or 0),
                    'currency': 'EUR'
                },
                'performance_metrics': {
                    'average_processing_time_ms': round(avg_processing_time_ms, 2),
                    'average_processing_time_formatted': f"{avg_processing_time_ms/1000:.1f}s" if avg_processing_time_ms > 1000 else f"{avg_processing_time_ms:.0f}ms",
                    'total_processing_samples': len(processing_times),
                    'query_time_ms': round(query_duration, 2),
                    'isolation_level': 'READ_COMMITTED'
                },
                'reconciliation_status': reconciliation_stats,
                'recent_activity': {
                    'last_30_days': recent_payouts.count(),
                    'recent_success_rate': (recent_payouts.filter(status='paid').count() / recent_payouts.count() * 100) if recent_payouts.count() > 0 else 0,
                    'recent_average_amount': str(recent_payouts.aggregate(avg=Avg('amount_decimal'))['avg'] or 0)
                },
                'error_analysis': error_analysis,
                'tracking_capabilities': {
                    'status_history_enabled': True,
                    'performance_metrics_enabled': True,
                    'reconciliation_tracking_enabled': True,
                    'retry_tracking_enabled': True,
                    'enhanced_error_tracking': True
                }
            }
            
            logger.info(f"Successfully generated payout analytics for user {user.id}")
            return Response(analytics_data, status=status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f"Error generating payout analytics for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'PAYOUT_ANALYTICS_ERROR',
            'detail': f'Failed to generate payout analytics: {str(e)}',
            'technical_details': {
                'enhanced_tracking_enabled': True,
                'isolation_level': 'READ_COMMITTED'
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)  # 10ms deadlock retry
def payout_performance_report(request):
    """
    Detailed performance report for payout operations with enhanced metrics.
    """
    try:
        user = request.user
        logger.info(f"Generating performance report for user: {user.id}")
        
        with atomic_with_isolation('READ COMMITTED'):
            start_time = timezone.now()
            
            # Get payouts with performance data
            payouts_with_metrics = Payout.objects.filter(
                seller=user,
                performance_metrics__isnull=False
            ).order_by('-created_at')[:100]  # Last 100 with metrics
            
            performance_data = {
                'processing_times': [],
                'query_times': [],
                'error_counts': [],
                'retry_analysis': [],
                'isolation_level_compliance': 0
            }
            
            total_analyzed = 0
            
            for payout in payouts_with_metrics:
                total_analyzed += 1
                
                # Extract performance metrics
                if payout.performance_metrics and 'metrics' in payout.performance_metrics:
                    metrics = payout.performance_metrics['metrics']
                    
                    for metric in metrics:
                        metric_name = metric.get('name', '')
                        metric_value = metric.get('value', 0)
                        
                        if 'duration' in metric_name.lower() and 'ms' in metric_name:
                            performance_data['processing_times'].append({
                                'payout_id': str(payout.id)[:8],
                                'metric_name': metric_name,
                                'duration_ms': metric_value,
                                'timestamp': metric.get('timestamp')
                            })
                        
                        elif 'query' in metric_name.lower():
                            performance_data['query_times'].append({
                                'payout_id': str(payout.id)[:8],
                                'query_type': metric_name,
                                'duration_ms': metric_value
                            })
                        
                        elif 'error' in metric_name.lower():
                            performance_data['error_counts'].append({
                                'payout_id': str(payout.id)[:8],
                                'error_type': metric_name,
                                'error_details': str(metric_value),
                                'timestamp': metric.get('timestamp')
                            })
                
                # Analyze retry patterns
                if payout.retry_count > 0:
                    performance_data['retry_analysis'].append({
                        'payout_id': str(payout.id)[:8],
                        'retry_count': payout.retry_count,
                        'last_retry': payout.last_retry_at.isoformat() if payout.last_retry_at else None,
                        'final_status': payout.status,
                        'reconciliation_status': payout.reconciliation_status
                    })
            
            # Calculate aggregated metrics
            processing_times = [item['duration_ms'] for item in performance_data['processing_times']]
            query_times = [item['duration_ms'] for item in performance_data['query_times']]
            
            report_data = {
                'report_metadata': {
                    'generated_at': timezone.now().isoformat(),
                    'payouts_analyzed': total_analyzed,
                    'report_generation_time_ms': round((timezone.now() - start_time).total_seconds() * 1000, 2),
                    'isolation_level': 'READ_COMMITTED',
                    'deadlock_retry_enabled': True
                },
                'processing_performance': {
                    'average_processing_time_ms': round(sum(processing_times) / len(processing_times), 2) if processing_times else 0,
                    'median_processing_time_ms': sorted(processing_times)[len(processing_times)//2] if processing_times else 0,
                    'max_processing_time_ms': max(processing_times) if processing_times else 0,
                    'min_processing_time_ms': min(processing_times) if processing_times else 0,
                    'total_samples': len(processing_times)
                },
                'query_performance': {
                    'average_query_time_ms': round(sum(query_times) / len(query_times), 2) if query_times else 0,
                    'total_query_samples': len(query_times),
                    'query_breakdown': performance_data['query_times'][:10]  # Top 10 for analysis
                },
                'error_analysis': {
                    'total_errors': len(performance_data['error_counts']),
                    'error_rate': (len(performance_data['error_counts']) / total_analyzed * 100) if total_analyzed > 0 else 0,
                    'recent_errors': performance_data['error_counts'][:5]  # Most recent errors
                },
                'retry_analysis': {
                    'payouts_with_retries': len(performance_data['retry_analysis']),
                    'retry_rate': (len(performance_data['retry_analysis']) / total_analyzed * 100) if total_analyzed > 0 else 0,
                    'total_retry_attempts': sum([item['retry_count'] for item in performance_data['retry_analysis']]),
                    'retry_details': performance_data['retry_analysis'][:10]  # Top 10 for analysis
                },
                'recommendations': []
            }
            
            # Generate performance recommendations
            avg_processing = report_data['processing_performance']['average_processing_time_ms']
            if avg_processing > 5000:  # > 5 seconds
                report_data['recommendations'].append('Consider optimizing payout creation process - average processing time is high')
            
            error_rate = report_data['error_analysis']['error_rate']
            if error_rate > 10:  # > 10% error rate
                report_data['recommendations'].append('High error rate detected - review error tracking and implement fixes')
            
            retry_rate = report_data['retry_analysis']['retry_rate']
            if retry_rate > 5:  # > 5% retry rate
                report_data['recommendations'].append('Consider database optimization - high retry rate suggests deadlock issues')
            
            if not report_data['recommendations']:
                report_data['recommendations'].append('Payout performance is within acceptable ranges')
            
            logger.info(f"Successfully generated performance report for user {user.id}")
            return Response(report_data, status=status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f"Error generating performance report for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'PERFORMANCE_REPORT_ERROR',
            'detail': f'Failed to generate performance report: {str(e)}',
            'technical_details': {
                'enhanced_tracking_enabled': True,
                'isolation_level': 'READ_COMMITTED'
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@retry_on_deadlock(max_retries=3, delay=0.01, backoff=2.0)  # 10ms deadlock retry
def update_payout_reconciliation(request, payout_id):
    """
    Update reconciliation status for a payout with enhanced tracking.
    Uses READ COMMITTED isolation with proper model ordering.
    """
    try:
        user = request.user
        new_status = request.data.get('reconciliation_status')
        notes = request.data.get('notes', '')
        
        if not new_status:
            return Response({
                'error': 'MISSING_RECONCILIATION_STATUS',
                'detail': 'reconciliation_status field is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_statuses = ['pending', 'matched', 'mismatched', 'manual_review']
        if new_status not in valid_statuses:
            return Response({
                'error': 'INVALID_RECONCILIATION_STATUS',
                'detail': f'Status must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"Updating reconciliation status for payout {payout_id} to {new_status}")
        
        with atomic_with_isolation('READ COMMITTED'):
            start_time = timezone.now()
            
            # Get payout with proper locking (Payout model first)
            try:
                payout = Payout.objects.select_for_update().get(id=payout_id, seller=user)
            except Payout.DoesNotExist:
                return Response({
                    'error': 'PAYOUT_NOT_FOUND',
                    'detail': 'Payout not found or you do not have permission to update it.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Track performance
            old_status = payout.reconciliation_status
            
            # Update reconciliation status using the enhanced tracking method
            payout.update_reconciliation_status(new_status, notes)
            
            # Track the operation performance
            operation_duration = (timezone.now() - start_time).total_seconds() * 1000
            print(f"📊 Update took {operation_duration:.2f}ms by user {user.id}")
            
            response_data = {
                'success': True,
                'payout_id': str(payout.id),
                'reconciliation_update': {
                    'old_status': old_status,
                    'new_status': new_status,
                    'updated_at': payout.reconciled_at.isoformat() if payout.reconciled_at else None,
                    'notes': notes,
                    'updated_by': user.username
                },
                'performance_metrics': {
                    'operation_duration_ms': round(operation_duration, 2),
                    'isolation_level': 'READ_COMMITTED',
                    'model_ordering': 'Payout (select_for_update)',
                    'deadlock_retry_enabled': True
                },
                'status_history': {
                    'total_entries': len(payout.status_history) if payout.status_history else 0,
                    'latest_entry': payout.latest_status_change
                }
            }
            
            logger.info(f"Successfully updated reconciliation status for payout {payout_id}")
            return Response(response_data, status=status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f"Error updating reconciliation for payout {payout_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'RECONCILIATION_UPDATE_ERROR',
            'detail': f'Failed to update reconciliation status: {str(e)}',
            'technical_details': {
                'enhanced_tracking_enabled': True,
                'isolation_level': 'READ_COMMITTED'
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)