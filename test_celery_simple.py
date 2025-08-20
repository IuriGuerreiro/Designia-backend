#!/usr/bin/env python3
"""
Simple Celery Task Testing

Quick tests for essential Celery functionality without creating database conflicts.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

def test_basic_connectivity():
    """Test basic Celery connectivity and task registration."""
    print("🔗 Testing Celery Connectivity...")
    
    try:
        from celery import current_app
        
        # Check broker connection
        broker_url = current_app.conf.broker_url
        print(f"   Broker: {broker_url}")
        
        # Check if workers are running
        inspect = current_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            print(f"   ✅ Connected to {len(stats)} worker(s)")
        else:
            print("   ⚠️  No active workers found")
        
        # Check registered tasks
        registered_tasks = list(current_app.tasks.keys())
        payment_tasks = [t for t in registered_tasks if 'payment_system' in t]
        
        print(f"   📋 Total registered tasks: {len(registered_tasks)}")
        print(f"   💰 Payment system tasks: {len(payment_tasks)}")
        
        for task in payment_tasks:
            print(f"      - {task}")
            
    except Exception as e:
        print(f"   ❌ Connectivity error: {e}")

def test_exchange_rate_task():
    """Test exchange rate task execution."""
    print("\n💱 Testing Exchange Rate Task...")
    
    try:
        from payment_system.services.exchange_rate_service import ExchangeRateService
        
        # Test with test data to avoid API limits
        result = ExchangeRateService.update_exchange_rates(
            force_update=True,
            use_test_data=True,
            source='manual_test',
            cleanup_old=False
        )
        
        if result.get('success'):
            print(f"   ✅ Update successful: {result.get('created_count', 0)} rates")
        else:
            print(f"   ❌ Update failed: {result.get('error')}")
            
    except Exception as e:
        print(f"   ❌ Exchange rate test error: {e}")

def test_payment_timeout_check():
    """Test payment timeout check without creating test data."""
    print("\n⏰ Testing Payment Timeout Check...")
    
    try:
        from payment_system.Tasks.payment_tasks import check_payment_timeouts_task
        
        # Run the task (it will find expired orders if any exist)
        result = check_payment_timeouts_task()
        
        if result and result.get('success'):
            print(f"   ✅ Check successful")
            print(f"   📊 Expired orders found: {result.get('total_expired', 0)}")
            print(f"   🚫 Orders cancelled: {len(result.get('cancelled_orders', []))}")
            print(f"   ⚠️  Errors encountered: {len(result.get('errors', []))}")
        else:
            error_msg = result.get('error') if result else 'No result returned'
            print(f"   ❌ Check failed: {error_msg}")
            
    except Exception as e:
        print(f"   ❌ Payment timeout test error: {e}")

def test_scheduler_status():
    """Test scheduler status."""
    print("\n📅 Testing Scheduler Status...")
    
    try:
        from payment_system.services.celery_scheduler_service import CelerySchedulerService
        
        status = CelerySchedulerService.get_task_status()
        
        if 'error' in status:
            print(f"   ❌ Error getting status: {status['error']}")
        else:
            print(f"   ✅ Scheduler accessible")
            print(f"   📈 Total tasks: {status.get('total_tasks', 0)}")
            print(f"   ✅ Enabled: {status.get('enabled_tasks', 0)}")
            print(f"   ❌ Disabled: {status.get('disabled_tasks', 0)}")
            
            for task in status.get('tasks', []):
                status_icon = "✅" if task.get('enabled') else "❌"
                print(f"      {status_icon} {task.get('name')}")
                print(f"         Schedule: {task.get('schedule')}")
                print(f"         Runs: {task.get('total_run_count', 0)}")
    
    except Exception as e:
        print(f"   ❌ Scheduler test error: {e}")

def test_async_task_execution():
    """Test async task execution."""
    print("\n🚀 Testing Async Task Execution...")
    
    try:
        from payment_system.services.celery_scheduler_service import CelerySchedulerService
        
        # Trigger an async task
        result = CelerySchedulerService.trigger_manual_update('exchange_rates')
        
        if result.get('success'):
            print(f"   ✅ Async task triggered successfully")
            print(f"   🆔 Task ID: {result.get('task_id')}")
            print("   📝 Note: Check Celery worker logs for execution details")
        else:
            print(f"   ❌ Failed to trigger task: {result.get('error')}")
            
    except Exception as e:
        print(f"   ❌ Async test error: {e}")

def main():
    """Run simple tests."""
    print("=" * 60)
    print("🧪 SIMPLE CELERY TESTING")
    print("=" * 60)
    
    test_basic_connectivity()
    test_exchange_rate_task()
    test_payment_timeout_check()
    test_scheduler_status()
    test_async_task_execution()
    
    print("\n" + "=" * 60)
    print("🏁 TESTING COMPLETE")
    print("=" * 60)
    print("\n💡 To run full Celery system:")
    print("   1. Make sure Redis is running: redis-server")
    print("   2. Start Celery worker: celery -A designiaBackend worker -l info")
    print("   3. Start Celery beat: celery -A designiaBackend beat -l info")
    print("   4. Monitor with: celery -A designiaBackend flower (optional)")

if __name__ == "__main__":
    main()