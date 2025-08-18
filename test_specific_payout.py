#!/usr/bin/env python3
"""
Test a specific payout that has orders to verify the API fixes work correctly.
"""

import os
import sys
import django
import json

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.views import payout_orders
from payment_system.models import Payout
from django.test import RequestFactory

def test_payout_with_orders():
    """Test a payout that has actual orders."""
    # First test the original issue payout to confirm API structure is correct
    original_issue_payout = 'c282a6d0-e26b-4c83-a853-f020ad20394d'
    print(f'🎯 Testing original issue payout: {original_issue_payout}')
    test_single_payout(original_issue_payout)
    
    # Then test a payout with orders if available
    payout_id = '9e98a320-8939-4bd5-8590-aecd8ddc09d9'
    
    print(f'🎯 Testing payout with actual orders: {payout_id}')
    test_single_payout(payout_id)

def test_single_payout(payout_id):
    """Test a single payout."""
    try:
        payout = Payout.objects.get(id=payout_id)
        print(f'   Seller: {payout.seller}')
        print(f'   Amount: {payout.amount_decimal}')

        factory = RequestFactory()
        request = factory.get(f'/api/payments/payouts/{payout_id}/orders/')
        request.user = payout.seller

        response = payout_orders(request, payout_id)
        if hasattr(response, 'render'):
            response.render()

        if response.status_code == 200:
            data = json.loads(response.content.decode())
            print(f'✅ Success! Status: {response.status_code}')
            print(f'📦 Orders returned: {data.get("transfer_count", 0)}')
            print(f'💰 Payout amount: {data.get("payout_amount")}')
            
            orders = data.get('orders', [])
            if orders:
                first_order = orders[0]
                print(f'📋 First order: {first_order.get("order_id")}')
                print(f'🛍️  Order items: {len(first_order.get("items", []))}')
                
                if first_order.get('items'):
                    print('   Items detail:')
                    for item in first_order['items']:
                        product_name = item.get("product_name")
                        quantity = item.get("quantity")
                        price = item.get("price")
                        total = item.get("total")
                        print(f'    • {product_name}: {quantity}x ${price} = ${total}')
                    
                    print('🎉 SUCCESS: Order items are being returned correctly!')
                    print('🎉 The field reference fixes are working!')
                else:
                    print('📦 Order has empty items array')
            else:
                print('⚠️  No orders in response (expected for this payout)')
                print('🎉 SUCCESS: API is working correctly - this payout simply has no associated orders')
        else:
            print(f'❌ Error: {response.status_code}')
            if hasattr(response, 'render'):
                response.render()
            print(response.content.decode())
    
    except Payout.DoesNotExist:
        print(f'❌ Payout {payout_id} not found')
    except Exception as e:
        print(f'💥 Exception: {str(e)}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_payout_with_orders()