#!/usr/bin/env python3
"""
Direct test of payment intent handling without decorators
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

def direct_handle_payment_intent_succeeded(payment_intent):
    """
    Handle payment_intent.succeeded without decorators - direct implementation
    """
    payment_intent_id = getattr(payment_intent, 'id', None)
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
    
    print(f"🔄 Processing payment intent: {payment_intent_id}")
    
    try:
        with transaction.atomic():
            # Update PaymentTracker records
            trackers = PaymentTracker.objects.filter(
                stripe_payment_intent_id=payment_intent_id
            ).select_for_update()
            
            print(f"   Found {trackers.count()} payment trackers")
            
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
                
                print(f"   ✅ Updated PaymentTracker {tracker.id}")
            
            # Update PaymentTransaction records
            transactions = PaymentTransaction.objects.filter(
                stripe_payment_intent_id=payment_intent_id
            ).select_for_update()
            
            print(f"   Found {transactions.count()} payment transactions")
            
            for payment_txn in transactions:
                print(f"   🔍 Processing transaction {payment_txn.id} (status: {payment_txn.status})")
                
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
                    
                    print(f"   ✅ Updated PaymentTransaction {payment_txn.id} to held status")
                    
                    # Update associated order status to payment_confirmed
                    if payment_txn.order:
                        order = payment_txn.order
                        
                        print(f"   🔍 Processing order {order.id} (status: {order.status})")
                        
                        # Update order status to payment_confirmed and payment_status to paid
                        if order.status == 'pending_payment':
                            order.status = 'payment_confirmed'
                            order.payment_status = 'paid'
                            order.processed_at = timezone.now()
                            order.admin_notes = f"{order.admin_notes}\\nPayment confirmed via payment intent {payment_intent_id}" if order.admin_notes else f"Payment confirmed via payment intent {payment_intent_id}"
                            
                            order.save(update_fields=[
                                'status', 'payment_status', 'processed_at', 'admin_notes', 'updated_at'
                            ])
                            results['orders_updated'] = results.get('orders_updated', 0) + 1
                            
                            print(f"   ✅ Updated Order {order.id} status to payment_confirmed and payment_status to paid")
                        else:
                            print(f"   ℹ️  Order {order.id} status is {order.status}, not pending_payment - skipped")
                else:
                    print(f"   ℹ️  Transaction {payment_txn.id} status is {payment_txn.status}, not pending/failed - skipped")
                
    except Exception as e:
        results['success'] = False
        results['errors'].append(f"Error updating payment intent succeeded: {str(e)}")
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    return results


class MockPaymentIntent:
    def __init__(self, intent_id):
        self.id = intent_id
        self.amount = 5000
        self.currency = 'usd'
        self.status = 'succeeded'
        self.charges = type('obj', (object,), {
            'data': [type('obj', (object,), {
                'id': 'ch_test',
                'payment_method': type('obj', (object,), {'id': 'pm_test'})()
            })()]
        })()


def test_direct_implementation():
    """Test the direct implementation without decorators"""
    print("🧪 Testing direct payment intent handling")
    print("=" * 60)
    
    # Find orders with the problematic state
    problematic_orders = Order.objects.filter(
        status='pending_payment',
        payment_status='paid'
    )
    
    print(f"Found {problematic_orders.count()} orders with inconsistent state")
    
    if problematic_orders.exists():
        order = problematic_orders.first()
        print(f"\\n🎯 Testing with Order: {order.id}")
        print(f"   Before: {order.status} / {order.payment_status}")
        
        # Get the payment transaction
        transaction_obj = order.payment_transactions.first()
        if transaction_obj:
            intent_id = transaction_obj.stripe_payment_intent_id
            print(f"   Payment Intent: {intent_id}")
            print(f"   Transaction Status: {transaction_obj.status}")
            
            # Create mock intent and test
            mock_intent = MockPaymentIntent(intent_id)
            
            print(f"\\n⚡ Running direct webhook handler...")
            try:
                result = direct_handle_payment_intent_succeeded(mock_intent)
                print(f"✅ Direct Result: {result}")
                
                # Check if order was updated
                order.refresh_from_db()
                transaction_obj.refresh_from_db()
                
                print(f"\\n📊 After Processing:")
                print(f"   Order: {order.status} / {order.payment_status}")
                print(f"   Transaction: {transaction_obj.status}")
                
                if order.status == 'payment_confirmed':
                    print(f"✅ SUCCESS: Order status correctly updated!")
                else:
                    print(f"❌ FAILED: Order status not updated")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    test_direct_implementation()