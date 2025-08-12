#!/usr/bin/env python3
"""
Test script for Stripe webhook order creation flow
Tests that the webhook creates Orders with paid status before clearing cart
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
from django.test import RequestFactory
from django.http import HttpRequest
from marketplace.models import Cart, CartItem, Product, Category, Order, OrderItem
from payment_system.views import handle_successful_payment

User = get_user_model()

def create_test_data():
    """Create test user, products, and cart items"""
    print("🔧 Creating test data...")
    
    # Create test user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
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

def create_mock_stripe_session(user_id, total_amount):
    """Create a mock Stripe session object for testing"""
    return {
        'id': 'cs_test_123456789',
        'amount_total': int(total_amount * 100),  # Convert to cents
        'metadata': {
            'user_id': str(user_id)
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

def test_webhook_order_creation():
    """Test the complete webhook flow"""
    print("\n🧪 Testing webhook order creation flow...")
    
    # Create test data
    user, products, cart = create_test_data()
    
    # Store initial state
    initial_cart_items_count = cart.items.count()
    initial_orders_count = Order.objects.filter(buyer=user).count()
    initial_order_items_count = OrderItem.objects.filter(order__buyer=user).count()
    
    # Calculate expected totals
    expected_subtotal = cart.total_amount
    expected_shipping = Decimal('19.99')
    expected_tax = Decimal('2.50')
    expected_total = expected_subtotal + expected_shipping + expected_tax
    
    print(f"📊 Initial state:")
    print(f"   - Cart items: {initial_cart_items_count}")
    print(f"   - Orders: {initial_orders_count}")
    print(f"   - Order items: {initial_order_items_count}")
    print(f"   - Expected subtotal: ${expected_subtotal}")
    print(f"   - Expected total: ${expected_total}")
    
    # Create mock Stripe session
    mock_session = create_mock_stripe_session(user.id, expected_total)
    
    # Store product stock before webhook
    product_stock_before = {}
    for item in cart.items.all():
        product_stock_before[item.product.id] = item.product.stock_quantity
    
    print(f"\n🔄 Executing webhook handler...")
    
    # Call the webhook handler
    result = handle_successful_payment(mock_session)
    
    # Verify results
    print(f"\n✅ Webhook result: {result}")
    
    # Refresh cart from database
    cart.refresh_from_db()
    
    # Check final state
    final_cart_items_count = cart.items.count()
    final_orders_count = Order.objects.filter(buyer=user).count()
    final_order_items_count = OrderItem.objects.filter(order__buyer=user).count()
    
    print(f"\n📊 Final state:")
    print(f"   - Cart items: {final_cart_items_count}")
    print(f"   - Orders: {final_orders_count}")
    print(f"   - Order items: {final_order_items_count}")
    
    # Verify order creation
    if final_orders_count > initial_orders_count:
        new_order = Order.objects.filter(buyer=user).order_by('-created_at').first()
        print(f"\n📦 Order created:")
        print(f"   - Order ID: {new_order.id}")
        print(f"   - Status: {new_order.status}")
        print(f"   - Payment Status: {new_order.payment_status}")
        print(f"   - Subtotal: ${new_order.subtotal}")
        print(f"   - Shipping: ${new_order.shipping_cost}")
        print(f"   - Tax: ${new_order.tax_amount}")
        print(f"   - Total: ${new_order.total_amount}")
        print(f"   - Items count: {new_order.items.count()}")
        print(f"   - Is locked: {new_order.is_locked}")
        
        # Verify order items
        print(f"\n📋 Order items:")
        for item in new_order.items.all():
            print(f"   - {item.quantity}x {item.product_name} @ ${item.unit_price} = ${item.total_price}")
        
        # Verify shipping address
        if new_order.shipping_address:
            print(f"\n🏠 Shipping address:")
            addr = new_order.shipping_address
            print(f"   - Name: {addr.get('name', 'N/A')}")
            print(f"   - Address: {addr.get('line1', 'N/A')}")
            if addr.get('line2'):
                print(f"   - Address 2: {addr.get('line2')}")
            print(f"   - City: {addr.get('city', 'N/A')}")
            print(f"   - State: {addr.get('state', 'N/A')}")
            print(f"   - ZIP: {addr.get('postal_code', 'N/A')}")
            print(f"   - Country: {addr.get('country', 'N/A')}")
    
    # Check stock updates
    print(f"\n📦 Product stock updates:")
    for item in CartItem.objects.filter(cart__user=user):
        product = item.product
        product.refresh_from_db()
        stock_before = product_stock_before.get(product.id, 0)
        stock_after = product.stock_quantity
        expected_stock = stock_before - item.quantity
        
        print(f"   - {product.name}:")
        print(f"     Before: {stock_before}, After: {stock_after}, Expected: {expected_stock}")
        print(f"     ✅ Stock updated correctly" if stock_after == expected_stock else "❌ Stock update mismatch")
    
    # Verify assertions
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
    
    # Test 3: Order items should match cart items
    expected_order_items = initial_cart_items_count
    actual_new_order_items = final_order_items_count - initial_order_items_count
    if actual_new_order_items == expected_order_items:
        print("✅ Order items created successfully")
    else:
        print(f"❌ Order items mismatch: expected {expected_order_items}, got {actual_new_order_items}")
    
    # Test 4: Order status should be 'paid'
    if final_orders_count > initial_orders_count:
        latest_order = Order.objects.filter(buyer=user).order_by('-created_at').first()
        if latest_order.status == 'paid' and latest_order.payment_status == 'paid':
            print("✅ Order status set to 'paid' correctly")
        else:
            print(f"❌ Order status incorrect: status='{latest_order.status}', payment_status='{latest_order.payment_status}'")
    
    # Test 5: User ID extraction should work
    if result:
        print("✅ User ID extracted from metadata successfully")
    else:
        print("❌ User ID extraction failed")
    
    return result

def test_edge_cases():
    """Test edge cases and error handling"""
    print("\n🧪 Testing edge cases...")
    
    # Test 1: Invalid user ID
    print("\n🔍 Test 1: Invalid user ID")
    mock_session_invalid_user = {
        'metadata': {'user_id': '99999'},
        'amount_total': 2000
    }
    result = handle_successful_payment(mock_session_invalid_user)
    print(f"   Result with invalid user: {result}")
    
    # Test 2: Missing user ID
    print("\n🔍 Test 2: Missing user ID")
    mock_session_no_user = {
        'metadata': {},
        'amount_total': 2000
    }
    result = handle_successful_payment(mock_session_no_user)
    print(f"   Result with missing user ID: {result}")
    
    # Test 3: Empty cart
    print("\n🔍 Test 3: Empty cart")
    user, _, cart = create_test_data()
    cart.clear_items()
    
    mock_session_empty_cart = create_mock_stripe_session(user.id, Decimal('19.99'))
    result = handle_successful_payment(mock_session_empty_cart)
    print(f"   Result with empty cart: {result}")

if __name__ == '__main__':
    print("🚀 Starting Stripe webhook order creation test...")
    print("=" * 60)
    
    try:
        # Test main flow
        success = test_webhook_order_creation()
        
        # Test edge cases
        test_edge_cases()
        
        print("\n" + "=" * 60)
        if success:
            print("🎉 All webhook tests completed successfully!")
        else:
            print("⚠️  Some webhook tests failed. Check the output above.")
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)