#!/usr/bin/env python3
"""
Comprehensive Celery Task Testing Script

Tests all aspects of the Celery implementation including:
- Task registration and execution
- Payment timeout logic
- Exchange rate updates
- Scheduled task functionality
"""

import os
import sys
import django
from datetime import timedelta, datetime
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import transaction
from marketplace.models import Order, OrderItem
from payment_system.models import PaymentTransaction, PaymentTracker
from payment_system.services.celery_scheduler_service import CelerySchedulerService
from django.contrib.auth import get_user_model

User = get_user_model()

def print_header(title):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print('='*60)

def print_step(step_num, description):
    """Print a test step."""
    print(f"\n📋 Step {step_num}: {description}")
    print('-' * 40)

def print_result(success, message):
    """Print test result."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")

class CeleryTester:
    """Comprehensive Celery testing class."""
    
    def __init__(self):
        self.test_user = None
        self.test_orders = []
        
    def run_all_tests(self):
        """Run all Celery tests."""
        print_header("CELERY TASK TESTING")
        
        # Test 1: Basic Celery connectivity
        self.test_celery_connectivity()
        
        # Test 2: Task registration
        self.test_task_registration()
        
        # Test 3: Manual task execution
        self.test_manual_task_execution()
        
        # Test 4: Payment timeout logic
        self.test_payment_timeout_logic()
        
        # Test 5: Exchange rate task
        self.test_exchange_rate_task()
        
        # Test 6: Scheduled task status
        self.test_scheduled_tasks()
        
        # Cleanup
        self.cleanup_test_data()
        
        print_header("TESTING COMPLETE")
        print("🎉 All tests completed! Check results above.")
        
    def test_celery_connectivity(self):
        """Test basic Celery connectivity."""
        print_step(1, "Testing Celery Connectivity")
        
        try:
            from celery import current_app
            
            # Test broker connection
            broker_url = current_app.conf.broker_url
            result_backend = current_app.conf.result_backend
            
            print(f"Broker URL: {broker_url}")
            print(f"Result Backend: {result_backend}")
            
            # Test inspection
            inspect = current_app.control.inspect()
            stats = inspect.stats()
            
            if stats:
                print_result(True, f"Connected to {len(stats)} Celery worker(s)")
                for worker_name in stats.keys():
                    print(f"   - Worker: {worker_name}")
            else:
                print_result(False, "No Celery workers found")
                
        except Exception as e:
            print_result(False, f"Celery connectivity error: {e}")
    
    def test_task_registration(self):
        """Test if our tasks are properly registered."""
        print_step(2, "Testing Task Registration")
        
        try:
            from celery import current_app
            
            # Get registered tasks
            registered = list(current_app.tasks.keys())
            
            # Check for our specific tasks
            expected_tasks = [
                'payment_system.Tasks.payment_tasks.check_payment_timeouts_task',
                'payment_system.Tasks.payment_tasks.cancel_expired_order',
                'payment_system.Tasks.exchange_rate_tasks.update_exchange_rates_task'
            ]
            
            print(f"Total registered tasks: {len(registered)}")
            
            for task_name in expected_tasks:
                if task_name in registered:
                    print_result(True, f"Task registered: {task_name}")
                else:
                    print_result(False, f"Task NOT registered: {task_name}")
            
            # Show all payment_system tasks
            payment_tasks = [t for t in registered if 'payment_system' in t]
            if payment_tasks:
                print("\n📝 All payment_system tasks:")
                for task in payment_tasks:
                    print(f"   - {task}")
            
        except Exception as e:
            print_result(False, f"Task registration error: {e}")
    
    def test_manual_task_execution(self):
        """Test manual execution of tasks."""
        print_step(3, "Testing Manual Task Execution")
        
        try:
            # Test exchange rate task
            print("🔄 Testing exchange rate task...")
            from payment_system.Tasks.exchange_rate_tasks import update_exchange_rates_task
            
            # Execute synchronously for testing
            result = update_exchange_rates_task()
            
            if result and result.get('success'):
                print_result(True, f"Exchange rate task: {result.get('message', 'Success')}")
                print(f"   Created/Updated: {result.get('created_count', 0)} rates")
            else:
                print_result(False, f"Exchange rate task failed: {result.get('error') if result else 'No result'}")
                
        except Exception as e:
            print_result(False, f"Manual task execution error: {e}")
    
    def test_payment_timeout_logic(self):
        """Test payment timeout logic with test data."""
        print_step(4, "Testing Payment Timeout Logic")
        
        try:
            # Create test user if not exists
            if not self.test_user:
                self.test_user, created = User.objects.get_or_create(
                    username='celery_test_user',
                    defaults={
                        'email': 'test@example.com',
                        'first_name': 'Test',
                        'last_name': 'User'
                    }
                )
                print(f"Test user {'created' if created else 'found'}: {self.test_user.username}")
            
            # Create a test order that's old enough to be expired (>3 days)
            old_date = timezone.now() - timedelta(days=4)
            
            with transaction.atomic():
                test_order = Order.objects.create(
                    buyer=self.test_user,
                    status='pending_payment',
                    payment_status='pending',
                    total_amount=99.99,
                    created_at=old_date
                )
                self.test_orders.append(test_order)
                
                # Create a test payment transaction
                payment_transaction = PaymentTransaction.objects.create(
                    order=test_order,
                    seller=self.test_user,  # Same user for simplicity
                    amount=99.99,
                    status='pending',
                    stripe_payment_intent_id='pi_test_timeout',
                    created_at=old_date
                )
                
                print(f"Created test order: {test_order.id} (4 days old)")
                print(f"Order status: {test_order.status}")
                print(f"Payment status: {test_order.payment_status}")
            
            # Test timeout check task
            print("\n🔄 Testing payment timeout check...")
            from payment_system.Tasks.payment_tasks import check_payment_timeouts_task
            
            result = check_payment_timeouts_task()
            
            if result and result.get('success'):
                print_result(True, "Payment timeout check executed successfully")
                print(f"   Found expired orders: {result.get('total_expired', 0)}")
                print(f"   Cancelled orders: {len(result.get('cancelled_orders', []))}")
                print(f"   Errors: {len(result.get('errors', []))}")
                
                # Check if our test order was cancelled
                test_order.refresh_from_db()
                if test_order.status == 'cancelled':
                    print_result(True, "Test order was correctly cancelled")
                    print(f"   Cancellation reason: {test_order.cancellation_reason}")
                else:
                    print_result(False, f"Test order status is still: {test_order.status}")
            else:
                print_result(False, f"Payment timeout check failed: {result.get('error') if result else 'No result'}")
                
        except Exception as e:
            print_result(False, f"Payment timeout test error: {e}")
            import traceback
            traceback.print_exc()
    
    def test_exchange_rate_task(self):
        """Test exchange rate task execution."""
        print_step(5, "Testing Exchange Rate Task")
        
        try:
            from payment_system.services.exchange_rate_service import ExchangeRateService
            
            # Get current status
            status = ExchangeRateService.get_exchange_rate_status()
            print(f"Exchange rate status: {status.get('status', 'unknown')}")
            print(f"Has data: {status.get('has_data', False)}")
            print(f"Last updated: {status.get('last_updated', 'Never')}")
            
            # Test update with test data
            print("\n🔄 Testing exchange rate update with test data...")
            result = ExchangeRateService.update_exchange_rates(
                force_update=True,
                use_test_data=True,
                source='celery_test'
            )
            
            if result.get('success'):
                print_result(True, "Exchange rate update successful")
                print(f"   Created/Updated: {result.get('created_count', 0)} rates")
                print(f"   Base currency: {result.get('base_currency', 'USD')}")
            else:
                print_result(False, f"Exchange rate update failed: {result.get('error')}")
                
        except Exception as e:
            print_result(False, f"Exchange rate test error: {e}")
    
    def test_scheduled_tasks(self):
        """Test scheduled task configuration."""
        print_step(6, "Testing Scheduled Task Configuration")
        
        try:
            # Get task status
            status = CelerySchedulerService.get_task_status()
            
            if 'error' in status:
                print_result(False, f"Error getting task status: {status['error']}")
                return
            
            print_result(True, f"Scheduler service accessible")
            print(f"   Total tasks: {status.get('total_tasks', 0)}")
            print(f"   Enabled tasks: {status.get('enabled_tasks', 0)}")
            print(f"   Disabled tasks: {status.get('disabled_tasks', 0)}")
            
            # Check individual tasks
            tasks = status.get('tasks', [])
            for task in tasks:
                enabled_status = "✅" if task.get('enabled') else "❌"
                print(f"   {enabled_status} {task.get('name', 'Unknown')}")
                print(f"      Schedule: {task.get('schedule', 'Unknown')}")
                print(f"      Run count: {task.get('total_run_count', 0)}")
            
            # Test manual trigger
            print("\n🔄 Testing manual task trigger...")
            trigger_result = CelerySchedulerService.trigger_manual_update('exchange_rates')
            
            if trigger_result.get('success'):
                print_result(True, "Manual task trigger successful")
                print(f"   Task ID: {trigger_result.get('task_id')}")
            else:
                print_result(False, f"Manual trigger failed: {trigger_result.get('error')}")
                
        except Exception as e:
            print_result(False, f"Scheduled task test error: {e}")
    
    def cleanup_test_data(self):
        """Clean up test data created during testing."""
        print_step(7, "Cleaning Up Test Data")
        
        try:
            # Delete test orders
            deleted_orders = 0
            for order in self.test_orders:
                try:
                    # Delete related payment transactions first
                    PaymentTransaction.objects.filter(order=order).delete()
                    order.delete()
                    deleted_orders += 1
                except Exception as e:
                    print(f"   Warning: Could not delete order {order.id}: {e}")
            
            # Optionally delete test user (commented out to avoid issues)
            # if self.test_user and self.test_user.username == 'celery_test_user':
            #     self.test_user.delete()
            #     print("   Deleted test user")
            
            print_result(True, f"Cleanup completed - deleted {deleted_orders} test orders")
            
        except Exception as e:
            print_result(False, f"Cleanup error: {e}")

def main():
    """Main testing function."""
    try:
        tester = CeleryTester()
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal testing error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()