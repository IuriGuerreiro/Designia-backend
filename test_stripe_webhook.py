#!/usr/bin/env python3
"""
Test script for debugging Stripe webhook events
"""

import os
import sys
import django
import json
from decimal import Decimal
from datetime import datetime

# Setup Django
sys.path.append('/mnt/f/Nigger/Projects/Programmes/WebApps/Desginia/Designia-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory, Client
from django.http import HttpRequest
from marketplace.models import Cart, CartItem, Product, Category, Order, OrderItem
from payment_system.views import handle_successful_payment

User = get_user_model()

def create_mock_checkout_session_completed_event():
    """Create a mock checkout.session.completed event for testing"""
    return {
        'id': 'cs_test_123456789',
        'object': 'checkout.session',
        'amount_total': 9643,  # $96.43 in cents
        'currency': 'usd',
        'payment_status': 'paid',
        'status': 'complete',
        'metadata': {
            'user_id': '9'
        },
        'shipping_details': {
            'name': 'Test User',
            'address': {
                'line1': '123 Test Street',
                'line2': 'Apt 4B',
                'city': 'Test City',
                'state': 'TC',
                'postal_code': '12345',
                'country': 'US'
            }
        },
        'customer_details': {
            'name': 'Test User',
            'email': 'test@example.com',
            'address': {
                'line1': '123 Test Street', 
                'line2': 'Apt 4B',
                'city': 'Test City',
                'state': 'TC',
                'postal_code': '12345',
                'country': 'US'
            }
        },
        'total_details': {
            'amount_tax': 250  # $2.50 in cents
        }
    }

def create_test_data():
    """Create test user and cart items for webhook testing"""
    print("🔧 Creating test data for webhook testing...")
    
    # Get or create test user
    user, created = User.objects.get_or_create(
        id=9,
        defaults={
            'username': 'testuser',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
    )
    
    if created:
        user.set_password('testpass123')
        user.save()
    
    # Create test category
    category, _ = Category.objects.get_or_create(
        name='Test Category',
        defaults={'description': 'Test category for webhook testing'}
    )
    
    # Create test products
    products = []
    for i in range(3):
        product, _ = Product.objects.get_or_create(
            name=f'Test Product {i+1}',
            defaults={
                'seller': user,
                'category': category,
                'description': f'Test product {i+1} for webhook testing',
                'price': Decimal(f'{10 + i}.99'),
                'stock_quantity': 50,
                'condition': 'new',
            }
        )
        products.append(product)
    
    # Get user's cart and add items
    cart = Cart.get_or_create_cart(user=user)
    cart.clear_items()  # Start fresh
    
    # Add products to cart
    for i, product in enumerate(products):
        cart_item, _ = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': i + 1}  # 1, 2, 3 quantities
        )
    
    print(f"✅ Test data created:")
    print(f"   - User: {user.username} (ID: {user.id})")
    print(f"   - Products: {len(products)}")
    print(f"   - Cart items: {cart.items.count()}")
    print(f"   - Cart total: ${cart.total_amount}")
    
    return user, products, cart

def test_checkout_session_completed_webhook():
    """Test the checkout.session.completed webhook event"""
    print("\n🧪 Testing checkout.session.completed webhook...")
    
    # Create test data
    user, products, cart = create_test_data()
    
    # Store initial state
    initial_cart_items_count = cart.items.count()
    initial_orders_count = Order.objects.filter(buyer=user).count()
    
    print(f"📊 Initial state:")
    print(f"   - Cart items: {initial_cart_items_count}")
    print(f"   - Orders: {initial_orders_count}")
    
    # Create mock checkout session completed event
    mock_session = create_mock_checkout_session_completed_event()
    
    print(f"\n🔄 Processing checkout.session.completed webhook...")
    print(f"Session data: {json.dumps(mock_session, indent=2)}")
    
    # Call the webhook handler directly
    result = handle_successful_payment(mock_session)
    
    # Refresh cart from database
    cart.refresh_from_db()
    
    # Check final state
    final_cart_items_count = cart.items.count()
    final_orders_count = Order.objects.filter(buyer=user).count()
    
    print(f"\n📊 Final state:")
    print(f"   - Cart items: {final_cart_items_count}")
    print(f"   - Orders: {final_orders_count}")
    print(f"   - Webhook result: {result}")
    
    # Verify order creation
    if final_orders_count > initial_orders_count:
        new_order = Order.objects.filter(buyer=user).order_by('-created_at').first()
        print(f"\n📦 Order created:")
        print(f"   - Order ID: {new_order.id}")
        print(f"   - Status: {new_order.status}")
        print(f"   - Payment Status: {new_order.payment_status}")
        print(f"   - Total: ${new_order.total_amount}")
        print(f"   - Items count: {new_order.items.count()}")
    
    # Verify results
    print(f"\n🔍 Verification:")
    
    # Test 1: Cart should be cleared
    if final_cart_items_count == 0:
        print("✅ Cart items cleared successfully")
    else:
        print(f"❌ Cart items not cleared: {final_cart_items_count} remaining")
    
    # Test 2: Order should be created
    if final_orders_count == initial_orders_count + 1:
        print("✅ Order created successfully")
    else:
        print(f"❌ Order creation failed: expected {initial_orders_count + 1}, got {final_orders_count}")
    
    # Test 3: Webhook should succeed
    if result:
        print("✅ Webhook processing successful")
    else:
        print("❌ Webhook processing failed")

def test_webhook_event_types():
    """Test different webhook event types"""
    print("\n🧪 Testing webhook event type handling...")
    
    # Test checkout.session.completed
    print("\n1. Testing checkout.session.completed event:")
    mock_session = create_mock_checkout_session_completed_event()
    
    # Simulate the webhook logic
    event_type = 'checkout.session.completed'
    print(f"   Event type: {event_type}")
    
    if event_type == 'checkout.session.completed':
        print("   ✅ Would call handle_successful_payment(session)")
        print("   ✅ Correct event type for our checkout flow")
    else:
        print("   ❌ Would not handle this event")
    
    # Test payment_intent.succeeded
    print("\n2. Testing payment_intent.succeeded event:")
    event_type = 'payment_intent.succeeded'
    print(f"   Event type: {event_type}")
    
    if event_type == 'checkout.session.completed':
        print("   ❌ Would call handle_successful_payment(session)")
    elif event_type == 'payment_intent.succeeded':
        print("   ℹ️ Would log but not process (waiting for checkout.session.completed)")
        print("   ✅ Correct behavior - we handle via checkout.session.completed")
    else:
        print("   ❌ Would not handle this event")

if __name__ == '__main__':
    print("🚀 Starting Stripe webhook debugging...")
    print("=" * 60)
    
    try:
        # Test event type handling
        test_webhook_event_types()
        
        # Test actual webhook processing
        test_checkout_session_completed_webhook()
        
        print("\n" + "=" * 60)
        print("🎉 Webhook debugging completed!")
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)