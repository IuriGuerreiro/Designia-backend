#!/usr/bin/env python3
"""
Manual test for payment timeout functionality
"""

import os
import sys
import django
from datetime import timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.utils import timezone
from django.db import transaction
from marketplace.models import Order

def manual_cancel_order(order_id):
    """Simple order cancellation without complex decorators."""
    try:
        with transaction.atomic():
            # Get the order with lock
            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                return {'success': False, 'error': 'Order not found', 'order_id': order_id}
            
            # Check if order is expired
            three_days_ago = timezone.now() - timedelta(days=3)
            
            if order.status != 'pending_payment':
                return {
                    'success': True,
                    'message': 'Order no longer pending payment',
                    'order_id': order_id,
                    'order_status': order.status
                }
            
            if order.created_at > three_days_ago:
                return {
                    'success': True,
                    'message': 'Order not yet expired',
                    'order_id': order_id,
                    'days_remaining': 3 - (timezone.now() - order.created_at).days
                }
            
            # Cancel the order
            order.status = 'cancelled'
            order.payment_status = 'failed'
            order.cancellation_reason = 'Payment timeout - Order cancelled after 3-day grace period'
            order.cancelled_at = timezone.now()
            order.admin_notes = f"{order.admin_notes}\nOrder automatically cancelled due to payment timeout (3 days)" if order.admin_notes else "Order automatically cancelled due to payment timeout (3 days)"
            
            order.save(update_fields=[
                'status', 'payment_status', 'cancellation_reason', 
                'cancelled_at', 'admin_notes', 'updated_at'
            ])
            
            print(f"✅ Successfully cancelled order {order_id}")
            
            return {
                'success': True,
                'message': 'Order cancelled due to payment timeout',
                'order_id': order_id,
                'cancelled_at': order.cancelled_at.isoformat()
            }
            
    except Exception as e:
        print(f"❌ Error cancelling order {order_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'order_id': order_id
        }

def manual_timeout_check():
    """Simple timeout check without complex decorators."""
    try:
        three_days_ago = timezone.now() - timedelta(days=3)
        
        expired_orders = Order.objects.filter(
            status='pending_payment',
            created_at__lte=three_days_ago
        )
        
        results = {
            'success': True,
            'total_expired': expired_orders.count(),
            'cancelled_orders': [],
            'errors': []
        }
        
        print(f"Found {results['total_expired']} expired orders to cancel")
        
        for order in expired_orders[:3]:  # Limit to first 3 for testing
            print(f"\n🔄 Processing order {order.id}...")
            print(f"   Created: {order.created_at}")
            print(f"   Status: {order.status}")
            print(f"   Payment Status: {order.payment_status}")
            
            cancel_result = manual_cancel_order(str(order.id))
            
            if cancel_result['success']:
                if 'cancelled_at' in cancel_result:
                    results['cancelled_orders'].append({
                        'order_id': str(order.id),
                        'cancelled_at': cancel_result.get('cancelled_at'),
                        'message': cancel_result.get('message')
                    })
                    print(f"   ✅ Cancelled successfully")
                else:
                    print(f"   ℹ️  {cancel_result.get('message')}")
            else:
                results['errors'].append({
                    'order_id': str(order.id),
                    'error': cancel_result.get('error', 'Unknown error')
                })
                print(f"   ❌ Error: {cancel_result.get('error')}")
        
        print(f"\n📊 Final Results:")
        print(f"   Total expired: {results['total_expired']}")
        print(f"   Successfully cancelled: {len(results['cancelled_orders'])}")
        print(f"   Errors: {len(results['errors'])}")
        
        return results
        
    except Exception as e:
        print(f"❌ Timeout check error: {e}")
        return {
            'success': False,
            'error': str(e),
            'total_expired': 0,
            'cancelled_orders': [],
            'errors': [{'error': str(e)}]
        }

def main():
    print("🧪 Manual Payment Timeout Test")
    print("=" * 50)
    
    result = manual_timeout_check()
    
    if result['success']:
        print("\n✅ Test completed successfully!")
    else:
        print(f"\n❌ Test failed: {result.get('error')}")

if __name__ == "__main__":
    main()