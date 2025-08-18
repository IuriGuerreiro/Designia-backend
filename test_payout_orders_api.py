#!/usr/bin/env python3
"""
Test script for payout orders API endpoint.

This script tests the specific endpoint mentioned in the issue:
GET /api/payments/payouts/{payout_id}/orders/
"""

import os
import sys
import django
import requests
import json
from datetime import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.models import Payout, PayoutItem
from marketplace.models import Order, OrderItem
from django.contrib.auth import get_user_model

User = get_user_model()

def test_payout_orders_api():
    """Test the payout orders API endpoint."""
    print("🔍 Testing Payout Orders API Endpoint")
    print("=" * 50)
    
    # Test the specific payout mentioned in the issue first
    specific_payout_id = "c282a6d0-e26b-4c83-a853-f020ad20394d"
    try:
        specific_payout = Payout.objects.get(id=specific_payout_id)
        print(f"🎯 Testing specific payout from issue: {specific_payout_id}")
        test_single_payout(specific_payout)
    except Payout.DoesNotExist:
        print(f"⚠️  Specific payout {specific_payout_id} not found")
    
    # Get test data
    payouts = Payout.objects.all()[:5]
    
    if not payouts:
        print("❌ No payouts found in database")
        return
    
    print(f"📊 Found {len(payouts)} payouts to test")
    
    for payout in payouts:
        test_single_payout(payout)

def test_single_payout(payout):
    """Test a single payout's orders endpoint."""
    print(f"\n🧪 Testing payout: {payout.id}")
    print(f"   Amount: {payout.amount_decimal}")
    print(f"   Status: {payout.status}")
    
    # Test the view directly
    try:
        from payment_system.views import payout_orders
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        
        # Create mock request
        factory = RequestFactory()
        request = factory.get(f'/api/payments/payouts/{payout.id}/orders/')
        request.user = payout.seller  # Set the seller as the user
        
        # Call the view
        response = payout_orders(request, payout.id)
        
        # Render the response if it's a TemplateResponse
        if hasattr(response, 'render'):
            response.render()
        
        if response.status_code == 200:
            data = json.loads(response.content.decode())
            print(f"   ✅ API Response: {response.status_code}")
            print(f"   📦 Orders returned: {data.get('transfer_count', 0)}")
            print(f"   💰 Payout amount: {data.get('payout_amount')}")
            
            # Check if orders have proper data
            orders = data.get('orders', [])
            if orders:
                first_order = orders[0]
                print(f"   📋 First order items: {len(first_order.get('items', []))}")
                if first_order.get('items'):
                    first_item = first_order['items'][0]
                    print(f"   🛍️  Sample item: {first_item.get('product_name')} - {first_item.get('price')}")
                else:
                    print("   📦 Order has no items array")
            else:
                print("   ⚠️  No orders found in response")
                
            # Show full response structure for debugging
            print(f"   🔍 Response keys: {list(data.keys())}")
            
        else:
            print(f"   ❌ API Error: {response.status_code}")
            try:
                # Render the response if it's a TemplateResponse
                if hasattr(response, 'render'):
                    response.render()
                error_data = json.loads(response.content.decode())
                print(f"   Error: {error_data}")
            except:
                try:
                    if hasattr(response, 'render'):
                        response.render()
                    print(f"   Raw error: {response.content.decode()}")
                except:
                    print(f"   Error accessing response content")
                
    except Exception as e:
        print(f"   💥 Exception: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎯 Test completed!")

def check_data_integrity():
    """Check data integrity for payout orders."""
    print("\n🔍 Checking Data Integrity")
    print("=" * 30)
    
    # Check PayoutItems
    payout_items = PayoutItem.objects.all()[:10]
    print(f"📊 Checking {len(payout_items)} payout items...")
    
    for item in payout_items:
        print(f"\nPayoutItem {item.id}:")
        print(f"  - Transfer: {item.payment_transfer}")
        
        if item.payment_transfer:
            order = item.payment_transfer.order
            print(f"  - Order: {order}")
            
            if order:
                # Check order items
                order_items = order.items.all()
                print(f"  - Order items: {order_items.count()}")
                
                for oi in order_items:
                    print(f"    * {oi.product_name}: {oi.quantity}x ${oi.unit_price} = ${oi.total_price}")
            else:
                print("  - ⚠️  No order found")
        else:
            print("  - ⚠️  No payment transfer found")

if __name__ == '__main__':
    test_payout_orders_api()
    check_data_integrity()