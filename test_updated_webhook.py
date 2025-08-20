#!/usr/bin/env python3
"""
Test the updated metadata-based webhook handler
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from marketplace.models import Order
from payment_system.views import handle_payment_intent_succeeded


class MockPaymentIntentWithMetadata:
    def __init__(self, intent_id, order_id=None):
        self.id = intent_id
        self.amount = 5000
        self.currency = 'usd'
        self.status = 'succeeded'
        
        # Set metadata with order_id
        self.metadata = {'order_id': order_id, 'user_id': '1'} if order_id else {}
        
        self.charges = type('obj', (object,), {
            'data': [type('obj', (object,), {
                'id': 'ch_test',
                'payment_method': type('obj', (object,), {'id': 'pm_test'})()
            })()]
        })()


def test_updated_webhook_handler():
    """Test the updated webhook handler"""
    print("🧪 Testing updated webhook handler with metadata validation")
    print("=" * 60)
    
    # Test 1: Payment intent WITHOUT metadata
    print("\\n1️⃣ Testing payment intent WITHOUT order_id metadata...")
    mock_intent_no_metadata = MockPaymentIntentWithMetadata('pi_test_no_metadata')
    result = handle_payment_intent_succeeded(mock_intent_no_metadata)
    
    print(f"   Result: {result}")
    
    if result.get('message') == 'Payment intent has no order_id in metadata - not processed':
        print("✅ PASS: Correctly skipped payment intent without metadata")
    else:
        print("❌ FAIL: Should have skipped payment intent without metadata")
    
    # Test 2: Payment intent WITH valid order_id metadata
    print("\\n2️⃣ Testing payment intent WITH valid order_id metadata...")
    
    # Create a test order in pending_payment status
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        test_user = User.objects.first()
        if not test_user:
            print("⚠️ No users found - skipping test with real order")
            return
            
        # Find or create a pending order
        pending_order = Order.objects.filter(status='pending_payment').first()
        
        if pending_order:
            print(f"   Using existing order: {pending_order.id}")
            print(f"   Current status: {pending_order.status} / {pending_order.payment_status}")
            
            mock_intent_with_metadata = MockPaymentIntentWithMetadata(
                'pi_test_with_metadata_real',
                str(pending_order.id)
            )
            
            result = handle_payment_intent_succeeded(mock_intent_with_metadata)
            print(f"   Result: {result}")
            
            if result['success'] and result.get('orders_updated', 0) > 0:
                print("✅ PASS: Successfully processed payment intent with metadata")
                
                # Check order status
                pending_order.refresh_from_db()
                print(f"   New status: {pending_order.status} / {pending_order.payment_status}")
            else:
                print("❌ FAIL: Failed to process payment intent with metadata")
        else:
            print("⚠️ No pending orders found - creating mock scenario")
            
            # Test with invalid order ID to ensure error handling works
            mock_intent_invalid = MockPaymentIntentWithMetadata(
                'pi_test_invalid_order',
                '00000000-0000-0000-0000-000000000000'
            )
            
            result = handle_payment_intent_succeeded(mock_intent_invalid)
            print(f"   Invalid order result: {result}")
            
            if not result['success'] and 'not found' in result.get('error', ''):
                print("✅ PASS: Correctly handled invalid order ID")
            else:
                print("❌ FAIL: Should have returned error for invalid order ID")
    
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_updated_webhook_handler()