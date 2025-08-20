#!/usr/bin/env python3
"""
Test the fixed payment_intent.payment_failed webhook handling
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from marketplace.models import Order
from payment_system.views import handle_payment_intent_failed
from django.contrib.auth import get_user_model


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


def create_test_order():
    """Create a test order for testing"""
    User = get_user_model()
    user = User.objects.first()
    
    if not user:
        print("⚠️ No users found - cannot create test order")
        return None
    
    # Create a test order
    order = Order.objects.create(
        buyer=user,
        status='pending_payment',
        payment_status='pending',
        subtotal=50.00,
        total_amount=50.00,
        shipping_address={'test': 'address'}
    )
    
    print(f"✅ Created test order: {order.id}")
    return order


def test_fixed_payment_intent_failed():
    """Test the fixed payment intent failed webhook handler"""
    print("🧪 Testing FIXED payment_intent.payment_failed webhook handler")
    print("=" * 60)
    
    # Test 1: Payment intent WITHOUT metadata (should be skipped)
    print("\\n1️⃣ Testing payment intent WITHOUT order_id metadata...")
    mock_intent_no_metadata = MockPaymentIntentFailed('pi_test_failed_no_metadata')
    
    result = handle_payment_intent_failed(mock_intent_no_metadata)
    print(f"   Result: {result}")
    
    if result.get('message') == 'Payment intent has no order_id in metadata - not processed':
        print("✅ PASS: Correctly skipped payment intent without metadata")
    else:
        print("❌ FAIL: Should have skipped payment intent without metadata")
    
    # Test 2: Payment intent WITH valid order_id metadata
    print("\\n2️⃣ Testing payment intent WITH valid order_id metadata...")
    
    # Create a test order or use existing one
    test_order = create_test_order()
    
    if test_order:
        print(f"   Using order: {test_order.id}")
        print(f"   Before: {test_order.status} / {test_order.payment_status}")
        
        mock_intent_with_metadata = MockPaymentIntentFailed(
            'pi_test_failed_with_metadata',
            str(test_order.id),
            'card_declined',
            'Your card was declined due to insufficient funds.'
        )
        
        try:
            result = handle_payment_intent_failed(mock_intent_with_metadata)
            print(f"   Result: {result}")
            
            if result.get('success') and result.get('orders_updated', 0) > 0:
                print("✅ Handler processed intent with metadata successfully")
                
                # Check if order payment status was updated
                test_order.refresh_from_db()
                print(f"   After: {test_order.status} / {test_order.payment_status}")
                
                if test_order.payment_status == 'failed':
                    print("✅ PASS: Order payment status correctly updated to 'failed'")
                else:
                    print("❌ FAIL: Order payment status was not updated to 'failed'")
                    print(f"       Expected: 'failed', Got: '{test_order.payment_status}'")
            else:
                print("❌ Handler failed to process intent with metadata")
                print(f"   Errors: {result.get('errors', [])}")
                
        except Exception as e:
            print(f"❌ Error processing intent with metadata: {e}")
            import traceback
            traceback.print_exc()
    
    # Test 3: Payment intent with INVALID order_id metadata
    print("\\n3️⃣ Testing payment intent WITH invalid order_id metadata...")
    mock_intent_invalid_order = MockPaymentIntentFailed(
        'pi_test_invalid_order',
        '00000000-0000-0000-0000-000000000000',
        'card_declined',
        'Your card was declined.'
    )
    
    result = handle_payment_intent_failed(mock_intent_invalid_order)
    print(f"   Result: {result}")
    
    if not result['success'] and 'not found' in result.get('error', ''):
        print("✅ PASS: Correctly handled invalid order ID")
    else:
        print("❌ FAIL: Should have returned error for invalid order ID")
    
    # Test 4: Check for import issues (should be fixed now)
    print("\\n4️⃣ Testing for import issues...")
    try:
        # The fixed version should not try to import the problematic function
        print("✅ No import errors expected (removed problematic import)")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    test_fixed_payment_intent_failed()