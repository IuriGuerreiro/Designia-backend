#!/usr/bin/env python3
"""
Test metadata-based payment intent handling
"""

import os
import django
from datetime import timezone, datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import transaction
from django.utils import timezone
from payment_system.models import PaymentTracker, PaymentTransaction
from marketplace.models import Order
import logging

logger = logging.getLogger(__name__)

def handle_payment_intent_succeeded_with_metadata(payment_intent):
    """
    Handle payment_intent.succeeded webhook events.
    Only processes payment intents that have order_id in metadata.
    Updates PaymentTracker and PaymentTransaction records with success status.
    """
    payment_intent_id = getattr(payment_intent, 'id', None)
    
    # Check if payment intent has metadata with order_id
    metadata = getattr(payment_intent, 'metadata', {})
    order_id = metadata.get('order_id') if metadata else None
    
    if not order_id:
        logger.info(f"Payment intent {payment_intent_id} has no order_id in metadata - skipping processing")
        return {
            'success': True,
            'message': 'Payment intent has no order_id in metadata - not processed',
            'trackers_updated': 0,
            'transactions_updated': 0,
            'orders_updated': 0,
            'errors': []
        }
    
    logger.info(f"Processing payment intent {payment_intent_id} for order {order_id}")
    
    amount = getattr(payment_intent, 'amount', 0)
    currency = getattr(payment_intent, 'currency', 'USD').upper()
    status_field = getattr(payment_intent, 'status', 'unknown')
    
    # Extract additional payment intent data
    latest_charge_id = ""
    payment_method_id = ""
    
    # Get latest charge info if available
    charges = getattr(payment_intent, 'charges', {})
    if charges and hasattr(charges, 'data') and charges.data:
        latest_charge = charges.data[0]
        latest_charge_id = getattr(latest_charge, 'id', '')
        payment_method_info = getattr(latest_charge, 'payment_method', None)
        if payment_method_info:
            payment_method_id = getattr(payment_method_info, 'id', '')
    
    results = {
        'success': True,
        'trackers_updated': 0,
        'transactions_updated': 0,
        'orders_updated': 0,
        'errors': []
    }
    
    try:
        with transaction.atomic():
            # First, get the specific order from metadata
            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                logger.error(f"Order {order_id} not found for payment intent {payment_intent_id}")
                return {
                    'success': False,
                    'error': f'Order {order_id} not found',
                    'trackers_updated': 0,
                    'transactions_updated': 0,
                    'orders_updated': 0,
                    'errors': [f'Order {order_id} not found']
                }
            
            # Only process if order is in pending_payment status
            if order.status != 'pending_payment':
                logger.info(f"Order {order_id} status is {order.status}, not pending_payment - skipping")
                return {
                    'success': True,
                    'message': f'Order {order_id} status is {order.status}, not pending_payment',
                    'trackers_updated': 0,
                    'transactions_updated': 0,
                    'orders_updated': 0,
                    'errors': []
                }
            
            print(f"✅ Found order {order_id} in pending_payment status")
            
            # Update PaymentTracker records for this payment intent
            trackers = PaymentTracker.objects.filter(
                stripe_payment_intent_id=payment_intent_id
            ).select_for_update()
            
            print(f"✅ Found {trackers.count()} payment trackers")
            
            for tracker in trackers:
                # Update tracker status and add payment intent details
                tracker.status = 'succeeded'
                tracker.latest_charge_id = latest_charge_id
                tracker.payment_method_id = payment_method_id
                
                # Clear any previous failure data
                tracker.failure_code = ''
                tracker.failure_reason = ''
                tracker.stripe_error_data = None
                
                tracker.save(update_fields=[
                    'status', 'latest_charge_id', 'payment_method_id',
                    'failure_code', 'failure_reason', 'stripe_error_data', 'updated_at'
                ])
                results['trackers_updated'] += 1
                
                logger.info(f"Updated PaymentTracker {tracker.id} to succeeded status")
            
            # Update PaymentTransaction records for this specific order
            transactions = PaymentTransaction.objects.filter(
                order=order,
                stripe_payment_intent_id=payment_intent_id
            ).select_for_update()
            
            print(f"✅ Found {transactions.count()} payment transactions for order")
            
            for payment_txn in transactions:
                # Update transaction status if it was pending or failed
                if payment_txn.status in ['pending', 'failed']:
                    payment_txn.status = 'held'  # Move to held status for 30-day hold
                    payment_txn.payment_received_date = timezone.now()
                    
                    # Start the hold period
                    if not payment_txn.hold_start_date:
                        payment_txn.start_hold(reason='standard', days=30, notes='Payment intent succeeded - starting hold period')
                    
                    # Clear any failure data
                    payment_txn.payment_failure_code = ''
                    payment_txn.payment_failure_reason = ''
                    
                    payment_txn.save(update_fields=[
                        'status', 'payment_received_date', 'payment_failure_code', 
                        'payment_failure_reason', 'updated_at'
                    ])
                    results['transactions_updated'] += 1
                    
                    logger.info(f"Updated PaymentTransaction {payment_txn.id} to held status")
            
            # Update the specific order status to payment_confirmed
            order.status = 'payment_confirmed'
            order.payment_status = 'paid'
            order.processed_at = timezone.now()
            order.admin_notes = f"{order.admin_notes}\\nPayment confirmed via payment intent {payment_intent_id}" if order.admin_notes else f"Payment confirmed via payment intent {payment_intent_id}"
            
            order.save(update_fields=[
                'status', 'payment_status', 'processed_at', 'admin_notes', 'updated_at'
            ])
            results['orders_updated'] = 1
            
            logger.info(f"Updated Order {order.id} status to payment_confirmed and payment_status to paid")
            
            print(f"✅ Successfully processed payment intent for order {order_id}")
                
    except Exception as e:
        results['success'] = False
        results['errors'].append(f"Error updating payment intent succeeded: {str(e)}")
        logger.error(f"Error in handle_payment_intent_succeeded: {e}")
        raise
    
    return results


class MockPaymentIntentWithMetadata:
    def __init__(self, intent_id, order_id=None):
        self.id = intent_id
        self.amount = 5000
        self.currency = 'usd'
        self.status = 'succeeded'
        
        # Set metadata with order_id
        self.metadata = {'order_id': order_id} if order_id else {}
        
        self.charges = type('obj', (object,), {
            'data': [type('obj', (object,), {
                'id': 'ch_test',
                'payment_method': type('obj', (object,), {'id': 'pm_test'})()
            })()]
        })()


def test_metadata_validation():
    """Test that webhook only processes intents with order_id in metadata"""
    print("🧪 Testing metadata validation")
    print("=" * 60)
    
    # Test 1: Payment intent WITHOUT metadata (should be skipped)
    print("\\n1️⃣ Testing payment intent WITHOUT order_id metadata...")
    mock_intent_no_metadata = MockPaymentIntentWithMetadata('pi_test_no_metadata')
    result = handle_payment_intent_succeeded_with_metadata(mock_intent_no_metadata)
    
    if result['message'] == 'Payment intent has no order_id in metadata - not processed':
        print("✅ PASS: Payment intent without metadata was correctly skipped")
    else:
        print("❌ FAIL: Payment intent without metadata was not skipped")
    
    # Test 2: Payment intent WITH valid order_id metadata
    print("\\n2️⃣ Testing payment intent WITH valid order_id metadata...")
    
    # Find an existing pending order
    pending_orders = Order.objects.filter(status='pending_payment')
    if pending_orders.exists():
        test_order = pending_orders.first()
        mock_intent_with_metadata = MockPaymentIntentWithMetadata(
            'pi_test_with_metadata', 
            str(test_order.id)
        )
        
        print(f"   Using order: {test_order.id}")
        print(f"   Current status: {test_order.status} / {test_order.payment_status}")
        
        result = handle_payment_intent_succeeded_with_metadata(mock_intent_with_metadata)
        
        if result['success'] and result['orders_updated'] > 0:
            print("✅ PASS: Payment intent with metadata was correctly processed")
            
            # Check order status
            test_order.refresh_from_db()
            print(f"   New status: {test_order.status} / {test_order.payment_status}")
        else:
            print("❌ FAIL: Payment intent with metadata was not processed correctly")
            print(f"   Result: {result}")
    else:
        print("⚠️ No pending orders found for testing")
    
    # Test 3: Payment intent with INVALID order_id metadata
    print("\\n3️⃣ Testing payment intent WITH invalid order_id metadata...")
    mock_intent_invalid_order = MockPaymentIntentWithMetadata(
        'pi_test_invalid_order', 
        '00000000-0000-0000-0000-000000000000'
    )
    
    result = handle_payment_intent_succeeded_with_metadata(mock_intent_invalid_order)
    
    if not result['success'] and 'Order 00000000-0000-0000-0000-000000000000 not found' in result.get('errors', []):
        print("✅ PASS: Payment intent with invalid order_id returned error")
    else:
        print("❌ FAIL: Payment intent with invalid order_id should have returned error")
        print(f"   Result: {result}")


if __name__ == "__main__":
    test_metadata_validation()