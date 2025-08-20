#!/usr/bin/env python3
"""
Debug script for payment_intent.succeeded webhook handling
Tests the actual webhook handler with real database data
"""

import os
import sys
import django
from datetime import timezone, datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import transaction
from payment_system.models import PaymentTracker, PaymentTransaction
from marketplace.models import Order
from payment_system.views import handle_payment_intent_succeeded


class MockPaymentIntent:
    """Mock Stripe payment intent object for testing"""
    
    def __init__(self, intent_id, amount=5000, currency='usd', status='succeeded', 
                 latest_charge_id='ch_test', payment_method_id='pm_test'):
        self.id = intent_id
        self.amount = amount
        self.currency = currency
        self.status = status
        
        # Mock charges data structure
        self.charges = type('obj', (object,), {
            'data': [type('obj', (object,), {
                'id': latest_charge_id,
                'payment_method': type('obj', (object,), {
                    'id': payment_method_id
                })()
            })()]
        })()


def test_existing_payment_intents():
    """Test payment intent handling with existing database records"""
    print("🔍 DEBUGGING PAYMENT INTENT HANDLING")
    print("=" * 60)
    
    # Find existing payment trackers and transactions
    trackers = PaymentTracker.objects.all()[:3]
    transactions = PaymentTransaction.objects.all()[:3]
    orders = Order.objects.filter(status='pending_payment')[:3]
    
    print(f"📊 Found {trackers.count()} payment trackers")
    print(f"📊 Found {transactions.count()} payment transactions") 
    print(f"📊 Found {orders.count()} pending payment orders")
    
    if not trackers.exists() and not transactions.exists():
        print("⚠️  No payment data found to test with")
        return
    
    # Test with an existing payment intent ID if available
    test_intent_id = None
    if trackers.exists():
        tracker = trackers.first()
        test_intent_id = tracker.stripe_payment_intent_id
        print(f"🎯 Testing with existing intent ID: {test_intent_id}")
    elif transactions.exists():
        transaction_obj = transactions.first()
        test_intent_id = transaction_obj.stripe_payment_intent_id
        print(f"🎯 Testing with existing intent ID: {test_intent_id}")
    
    if test_intent_id:
        # Check current state before processing
        print(f"\n🔍 BEFORE PROCESSING:")
        check_payment_state(test_intent_id)
        
        # Create mock payment intent
        mock_intent = MockPaymentIntent(
            intent_id=test_intent_id,
            amount=5000,
            currency='usd',
            status='succeeded'
        )
        
        # Process the webhook
        print(f"\n⚡ PROCESSING WEBHOOK...")
        try:
            result = handle_payment_intent_succeeded(mock_intent)
            print(f"✅ Webhook processing result: {result}")
        except Exception as e:
            print(f"❌ Webhook processing error: {e}")
            import traceback
            traceback.print_exc()
        
        # Check state after processing
        print(f"\n🔍 AFTER PROCESSING:")
        check_payment_state(test_intent_id)


def check_payment_state(payment_intent_id):
    """Check the current state of payment records"""
    print(f"   Payment Intent ID: {payment_intent_id}")
    
    # Check trackers
    trackers = PaymentTracker.objects.filter(stripe_payment_intent_id=payment_intent_id)
    print(f"   📋 Payment Trackers ({trackers.count()}):")
    for tracker in trackers:
        print(f"      ID: {tracker.id}, Status: {tracker.status}")
        print(f"      User: {tracker.user}, Created: {tracker.created_at}")
    
    # Check transactions
    transactions = PaymentTransaction.objects.filter(stripe_payment_intent_id=payment_intent_id)
    print(f"   💳 Payment Transactions ({transactions.count()}):")
    for txn in transactions:
        print(f"      ID: {txn.id}, Status: {txn.status}")
        print(f"      Net: ${txn.net_amount}, Hold Status: {txn.hold_status}")
        if txn.order:
            print(f"      Order: {txn.order.id}, Status: {txn.order.status}, Payment: {txn.order.payment_status}")
    
    # Check orders
    orders = Order.objects.filter(payment_transactions__stripe_payment_intent_id=payment_intent_id).distinct()
    print(f"   📦 Related Orders ({orders.count()}):")
    for order in orders:
        print(f"      ID: {order.id}, Status: {order.status}")
        print(f"      Payment Status: {order.payment_status}, Total: {order.total_amount}")


def simulate_payment_intent_succeeded():
    """Simulate a payment_intent.succeeded webhook with dummy data"""
    print(f"\n🧪 SIMULATING PAYMENT_INTENT.SUCCEEDED WEBHOOK")
    print("=" * 60)
    
    # Create a mock payment intent ID
    test_intent_id = "pi_test_debug_12345"
    
    # Create mock payment intent
    mock_intent = MockPaymentIntent(
        intent_id=test_intent_id,
        amount=2500,  # $25.00
        currency='usd',
        status='succeeded'
    )
    
    print(f"🎯 Mock Payment Intent: {test_intent_id}")
    print(f"   Amount: ${mock_intent.amount / 100:.2f}")
    print(f"   Currency: {mock_intent.currency.upper()}")
    print(f"   Status: {mock_intent.status}")
    
    # Check if there are any existing records for this ID
    existing_trackers = PaymentTracker.objects.filter(stripe_payment_intent_id=test_intent_id)
    existing_transactions = PaymentTransaction.objects.filter(stripe_payment_intent_id=test_intent_id)
    
    if existing_trackers.exists() or existing_transactions.exists():
        print(f"⚠️  Found existing records for this test intent ID")
        print(f"   Trackers: {existing_trackers.count()}")
        print(f"   Transactions: {existing_transactions.count()}")
        
        print(f"\n🔍 BEFORE PROCESSING:")
        check_payment_state(test_intent_id)
    else:
        print(f"ℹ️  No existing records for test intent ID (this is expected for simulation)")
    
    # Process the webhook
    print(f"\n⚡ PROCESSING SIMULATED WEBHOOK...")
    try:
        result = handle_payment_intent_succeeded(mock_intent)
        print(f"✅ Simulation result: {result}")
        
        if result.get('success'):
            print(f"   ✅ Trackers updated: {result.get('trackers_updated', 0)}")
            print(f"   ✅ Transactions updated: {result.get('transactions_updated', 0)}")
            print(f"   ✅ Orders updated: {result.get('orders_updated', 0)}")
        else:
            print(f"   ❌ Errors: {result.get('errors', [])}")
            
    except Exception as e:
        print(f"❌ Simulation error: {e}")
        import traceback
        traceback.print_exc()


def analyze_order_payment_flow():
    """Analyze the complete order payment flow"""
    print(f"\n📊 ANALYZING ORDER PAYMENT FLOW")
    print("=" * 60)
    
    # Find orders in different states
    pending_orders = Order.objects.filter(status='pending_payment')
    confirmed_orders = Order.objects.filter(status='payment_confirmed')
    
    print(f"📦 Orders Analysis:")
    print(f"   Pending Payment: {pending_orders.count()}")
    print(f"   Payment Confirmed: {confirmed_orders.count()}")
    
    # Analyze order-transaction relationships
    orders_with_transactions = Order.objects.filter(payment_transactions__isnull=False).distinct()
    orders_without_transactions = Order.objects.filter(payment_transactions__isnull=True)
    
    print(f"   With Payment Transactions: {orders_with_transactions.count()}")
    print(f"   Without Payment Transactions: {orders_without_transactions.count()}")
    
    # Show sample pending orders with their transaction details
    print(f"\n🔍 SAMPLE PENDING ORDERS:")
    for order in pending_orders[:3]:
        print(f"   Order {order.id}:")
        print(f"      Status: {order.status}, Payment Status: {order.payment_status}")
        print(f"      Created: {order.created_at}")
        
        transactions = order.payment_transactions.all()
        print(f"      Payment Transactions ({transactions.count()}):")
        for txn in transactions:
            print(f"         {txn.id}: {txn.status}, Intent: {txn.stripe_payment_intent_id}")


def main():
    """Run all debug tests"""
    print("🧪 PAYMENT INTENT DEBUG SUITE")
    print("=" * 60)
    
    analyze_order_payment_flow()
    test_existing_payment_intents()
    simulate_payment_intent_succeeded()
    
    print(f"\n📋 DEBUGGING RECOMMENDATIONS:")
    print(f"   1. Check that orders have payment_transactions linked")
    print(f"   2. Verify payment_intent IDs match between trackers and transactions")
    print(f"   3. Confirm transaction statuses allow order updates")
    print(f"   4. Test with real Stripe webhook data")
    print(f"   5. Monitor logs during actual payment processing")


if __name__ == "__main__":
    main()