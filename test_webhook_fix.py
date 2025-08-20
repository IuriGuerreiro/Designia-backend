#!/usr/bin/env python3
"""
Simple test to fix payment_intent.succeeded webhook handling
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import transaction
from payment_system.models import PaymentTracker, PaymentTransaction
from marketplace.models import Order
from payment_system.views import handle_payment_intent_succeeded


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


def test_with_real_data():
    """Test with actual inconsistent data from database"""
    print("🧪 Testing webhook handler with real inconsistent data")
    print("=" * 60)
    
    # Find orders with the problematic state
    problematic_orders = Order.objects.filter(
        status='pending_payment',
        payment_status='paid'
    )
    
    print(f"Found {problematic_orders.count()} orders with inconsistent state")
    
    if problematic_orders.exists():
        order = problematic_orders.first()
        print(f"\n🎯 Testing with Order: {order.id}")
        print(f"   Current State: {order.status} / {order.payment_status}")
        
        # Get the payment transaction
        transaction_obj = order.payment_transactions.first()
        if transaction_obj:
            intent_id = transaction_obj.stripe_payment_intent_id
            print(f"   Payment Intent: {intent_id}")
            print(f"   Transaction Status: {transaction_obj.status}")
            
            # Create mock intent and test
            mock_intent = MockPaymentIntent(intent_id)
            
            print(f"\n⚡ Running webhook handler...")
            try:
                result = handle_payment_intent_succeeded(mock_intent)
                print(f"✅ Result: {result}")
                
                # Check if order was updated
                order.refresh_from_db()
                transaction_obj.refresh_from_db()
                
                print(f"\n📊 After Processing:")
                print(f"   Order Status: {order.status} / {order.payment_status}")
                print(f"   Transaction Status: {transaction_obj.status}")
                
                if order.status == 'payment_confirmed':
                    print(f"✅ SUCCESS: Order status correctly updated!")
                else:
                    print(f"❌ FAILED: Order still has incorrect status")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    test_with_real_data()