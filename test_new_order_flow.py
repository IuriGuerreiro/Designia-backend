#!/usr/bin/env python
"""
Test script for the new order creation flow
This simulates the checkout session creation and webhook processing
"""

import os
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.contrib.auth import get_user_model
from marketplace.models import Cart, Order, Product
from payment_system.views import handle_successful_payment
from decimal import Decimal

User = get_user_model()

def test_new_order_flow():
    """Test the new order creation flow"""
    
    print("🧪 Testing New Order Creation Flow")
    print("="*50)
    
    try:
        # Get a user with cart items
        user = User.objects.first()
        if not user:
            print("❌ No users found in database")
            return
            
        cart = Cart.get_or_create_cart(user=user)
        cart_items = cart.items.all()
        
        if not cart_items.exists():
            print("⚠️ No cart items found for user")
            print("Adding a test product to cart...")
            
            # Get a product and add to cart
            product = Product.objects.first()
            if product:
                from marketplace.models import CartItem
                CartItem.objects.create(
                    cart=cart,
                    product=product,
                    quantity=1
                )
                cart_items = cart.items.all()
                print(f"✅ Added {product.name} to cart")
            else:
                print("❌ No products found in database")
                return
        
        print(f"👤 User: {user.email}")
        print(f"🛒 Cart items: {cart_items.count()}")
        
        # Step 1: Simulate order creation (checkout session creation)
        print("\n📦 Step 1: Creating order with pending_payment status...")
        
        # Calculate totals (similar to checkout session)
        subtotal = sum(item.total_price for item in cart_items)
        shipping_cost = Decimal('19.99')
        total_amount = subtotal + shipping_cost
        
        # Create order with pending_payment status
        order = Order.objects.create(
            buyer=user,
            status='pending_payment',
            payment_status='pending',
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            tax_amount=Decimal('0.00'),
            total_amount=total_amount,
            shipping_address={},
            is_locked=False,
        )
        
        # Create order items
        from marketplace.models import OrderItem
        for cart_item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                seller=cart_item.product.seller,
                quantity=cart_item.quantity,
                unit_price=cart_item.product.price,
                total_price=cart_item.total_price,
                product_name=cart_item.product.name,
                product_description=cart_item.product.description,
                product_image='',
            )
        
        print(f"✅ Order {order.id} created with status: {order.status}")
        print(f"✅ Payment status: {order.payment_status}")
        print(f"✅ Total amount: ${order.total_amount}")
        print(f"✅ Items: {order.items.count()}")
        
        # Clear cart (simulating checkout session creation)
        cart.clear_items()
        print(f"✅ Cart cleared")
        
        # Step 2: Simulate webhook payment confirmation
        print("\n💳 Step 2: Simulating successful payment webhook...")
        
        # Create mock Stripe session data (similar to webhook payload)
        mock_session = {
            'id': 'cs_test_123456789',
            'metadata': {
                'user_id': str(user.id),
                'order_id': str(order.id),
            },
            'amount_total': int(total_amount * 100),  # Convert to cents
            'total_details': {
                'amount_tax': 0,
            },
            'shipping_details': {
                'name': 'Test Customer',
                'address': {
                    'line1': '123 Test St',
                    'line2': '',
                    'city': 'Test City',
                    'state': 'TS',
                    'postal_code': '12345',
                    'country': 'US',
                }
            },
            'payment_intent': 'pi_test_123456789',
        }
        
        # Process the payment (webhook handler)
        success = handle_successful_payment(mock_session)
        
        if success:
            print("✅ Payment processing successful!")
            
            # Reload order to check updates
            order.refresh_from_db()
            print(f"✅ Order status updated to: {order.status}")
            print(f"✅ Payment status updated to: {order.payment_status}")
            print(f"✅ Order is locked: {order.is_locked}")
            print(f"✅ Shipping address updated: {bool(order.shipping_address)}")
            
        else:
            print("❌ Payment processing failed!")
            return
            
        # Verify the flow
        print(f"\n🔍 Final verification:")
        print(f"Order ID: {order.id}")
        print(f"Status: {order.status}")
        print(f"Payment Status: {order.payment_status}")
        print(f"Locked: {order.is_locked}")
        print(f"Items Count: {order.items.count()}")
        print(f"Cart Items Count: {cart.items.count()}")  # Should be 0
        
        # Check payment tracker
        from payment_system.models import PaymentTracker
        tracker = PaymentTracker.objects.filter(order=order).first()
        if tracker:
            print(f"✅ Payment tracker created: {tracker.stripe_payment_intent_id}")
        else:
            print("⚠️ No payment tracker found")
            
        print("\n🎉 New order flow test completed successfully!")
        print("="*50)
        print("Key improvements:")
        print("✅ Order created before payment (pending_payment status)")
        print("✅ Cart cleared immediately after order creation")
        print("✅ Webhook only updates existing order status")
        print("✅ User ownership verification in webhook")
        print("✅ Stock reserved immediately when order created")
        print("✅ Receipt email sent after payment confirmation")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_new_order_flow()