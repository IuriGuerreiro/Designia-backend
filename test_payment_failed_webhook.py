#!/usr/bin/env python3
"""
Test payment_intent.payment_failed webhook handling
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from marketplace.models import Order
from payment_system.views import handle_payment_intent_failed


class MockPaymentIntentFailed:
    def __init__(self, intent_id, order_id=None, error_code='card_declined', error_message='Your card was declined.'):
        self.id = intent_id
        self.amount = 5000
        self.currency = 'usd'
        self.status = 'requires_payment_method'
        
        # Set metadata with order_id
        self.metadata = {'order_id': order_id, 'user_id': '1'} if order_id else {}
        
        # Mock error data
        self.last_payment_error = type('obj', (object,), {
            'code': error_code,
            'message': error_message,
            'type': 'card_error',
            'decline_code': 'insufficient_funds',
            'param': None,
            'charge': None,
            'payment_method': {'type': 'card'}
        })()


def test_payment_intent_failed_handler():
    """Test the payment intent failed webhook handler"""
    print("🧪 Testing payment_intent.payment_failed webhook handler")
    print("=" * 60)
    
    # Test 1: Payment intent WITHOUT metadata
    print("\\n1️⃣ Testing payment intent WITHOUT order_id metadata...")
    mock_intent_no_metadata = MockPaymentIntentFailed('pi_test_failed_no_metadata')
    
    try:
        result = handle_payment_intent_failed(mock_intent_no_metadata)
        print(f"   Result: {result}")
        
        # This should process because there's no metadata validation
        if result.get('success'):
            print("⚠️  WARNING: Handler processed intent without metadata (should be skipped)")
        else:
            print("❌ Handler failed without metadata")
    except Exception as e:
        print(f"❌ Error processing intent without metadata: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Payment intent WITH valid order_id metadata
    print("\\n2️⃣ Testing payment intent WITH valid order_id metadata...")
    
    # Find a pending order to test with
    pending_order = Order.objects.filter(status='pending_payment').first()
    
    if pending_order:
        print(f"   Using order: {pending_order.id}")
        print(f"   Current status: {pending_order.status} / {pending_order.payment_status}")
        
        mock_intent_with_metadata = MockPaymentIntentFailed(
            'pi_test_failed_with_metadata',
            str(pending_order.id),
            'card_declined',
            'Your card was declined due to insufficient funds.'
        )
        
        try:
            result = handle_payment_intent_failed(mock_intent_with_metadata)
            print(f"   Result: {result}")
            
            if result.get('success'):
                print("✅ Handler processed intent with metadata successfully")
                
                # Check if order payment status was updated
                pending_order.refresh_from_db()
                print(f"   New status: {pending_order.status} / {pending_order.payment_status}")
                
                if pending_order.payment_status == 'failed':
                    print("✅ PASS: Order payment status correctly updated to 'failed'")
                else:
                    print("❌ FAIL: Order payment status was not updated to 'failed'")
                    print(f"       Expected: 'failed', Got: '{pending_order.payment_status}'")
            else:
                print("❌ Handler failed to process intent with metadata")
                print(f"   Errors: {result.get('errors', [])}")
                
        except Exception as e:
            print(f"❌ Error processing intent with metadata: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("⚠️ No pending orders found for testing")
    
    # Test 3: Check for import issues
    print("\\n3️⃣ Testing for import issues...")
    try:
        from payment_system.Tasks.payment_tasks import schedule_payment_timeout_check
        print("✅ schedule_payment_timeout_check import successful")
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("   This could be why the webhook handler fails!")


def test_order_payment_status_logic():
    """Test the specific logic for updating order payment status"""
    print("\\n🧪 Testing order payment status update logic")
    print("=" * 60)
    
    # Find orders and their payment transactions
    orders_with_transactions = Order.objects.filter(
        payment_transactions__isnull=False
    ).distinct()[:3]
    
    print(f"Found {orders_with_transactions.count()} orders with payment transactions")
    
    for order in orders_with_transactions:
        print(f"\\n📦 Order {order.id}:")
        print(f"   Status: {order.status} / {order.payment_status}")
        
        all_transactions = order.payment_transactions.all()
        failed_transactions = all_transactions.filter(status='failed')
        
        print(f"   Total transactions: {all_transactions.count()}")
        print(f"   Failed transactions: {failed_transactions.count()}")
        
        # Check the logic condition
        if len(failed_transactions) == len(all_transactions):
            print(f"   ✅ All transactions failed - order payment status should be 'failed'")
        else:
            print(f"   ℹ️  Not all transactions failed - order payment status unchanged")


if __name__ == "__main__":
    test_payment_intent_failed_handler()
    test_order_payment_status_logic()