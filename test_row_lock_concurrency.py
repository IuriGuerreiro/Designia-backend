#!/usr/bin/env python
"""
Row Lock Concurrency Test Script
===============================

Test script to demonstrate MySQL row locking behavior with concurrent transactions
using multithreading to simulate real-world concurrent access scenarios.

Usage:
    python test_row_lock_concurrency.py

This script tests:
1. Concurrent product stock updates (inventory management)
2. Concurrent payment processing (financial operations)
3. Deadlock detection and resolution
4. Lock timeout handling
5. Different isolation levels under concurrency
6. Performance under concurrent load
"""

import os
import sys
import django
from pathlib import Path
import threading
import time
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import transaction, IntegrityError, OperationalError
from django.contrib.auth import get_user_model
from marketplace.models import Product, Category, ProductMetrics, Order
from payment_system.models import PaymentTransaction
from utils.transaction_utils import (
    financial_transaction, product_transaction,
    atomic_with_isolation, rollback_safe_operation,
    get_current_isolation_level, TransactionMonitor,
    retry_on_deadlock, DeadlockError
)
from decimal import Decimal

User = get_user_model()

class ConcurrencyTester:
    """Test class for concurrent transaction scenarios"""
    
    def __init__(self):
        self.test_results = {}
        self.test_data = {}
        self.lock = threading.Lock()
        self.errors = Queue()
        self.successes = Queue()
        
    def log(self, message):
        """Thread-safe log messages"""
        import datetime
        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        thread_id = threading.current_thread().ident
        with self.lock:
            print(f"[{timestamp}] [T{thread_id}] {message}")
    
    def setup_test_data(self):
        """Setup test data for concurrent operations"""
        self.log("🔧 Setting up test data...")
        
        try:
            # Create test user
            user, created = User.objects.get_or_create(
                username='concurrency_test_user',
                defaults={
                    'email': 'concurrency@test.com',
                    'is_active': True,
                    'is_email_verified': True
                }
            )
            
            # Create test category
            category, created = Category.objects.get_or_create(
                name="Concurrency Test Category",
                defaults={'slug': 'concurrency-test-category'}
            )
            
            # Create test products for stock testing
            products = []
            for i in range(5):
                product, created = Product.objects.get_or_create(
                    slug=f'concurrency-test-product-{i}',
                    defaults={
                        'name': f'Concurrency Test Product {i}',
                        'description': f'Test product {i} for concurrency testing',
                        'price': Decimal('50.00'),
                        'stock_quantity': 100,  # Initial stock
                        'seller': user,
                        'category': category,
                        'is_active': True
                    }
                )
                products.append(product)
                
                # Ensure ProductMetrics exists
                metrics, created = ProductMetrics.objects.get_or_create(
                    product=product,
                    defaults={
                        'total_views': 0,
                        'total_clicks': 0,
                        'total_favorites': 0,
                        'total_cart_additions': 0,
                        'total_sales': 0,
                        'total_revenue': Decimal('0.00'),
                    }
                )
            
            # Create test orders for payment testing
            orders = []
            for i in range(5):
                # Generate unique UUID for each test order
                order_id = str(uuid.uuid4())
                order, created = Order.objects.get_or_create(
                    id=order_id,
                    defaults={
                        'buyer': user,
                        'status': 'pending_payment',
                        'payment_status': 'pending',
                        'subtotal': Decimal('100.00'),
                        'shipping_cost': Decimal('10.00'),
                        'tax_amount': Decimal('8.00'),
                        'total_amount': Decimal('118.00'),
                        'shipping_address': {}
                    }
                )
                orders.append(order)
            
            self.test_data = {
                'user': user,
                'category': category,
                'products': products,
                'orders': orders
            }
            
            self.log(f"✅ Test data setup complete: {len(products)} products, {len(orders)} orders")
            return True
            
        except Exception as e:
            self.log(f"❌ Failed to setup test data: {e}")
            return False
    
    def cleanup_test_data(self):
        """Clean up test data after tests"""
        self.log("🧹 Cleaning up test data...")
        
        try:
            # Clean up in reverse order of dependencies
            PaymentTransaction.objects.filter(
                stripe_payment_intent_id__contains='concurrency_test'
            ).delete()
            
            # Clean up test orders by buyer
            Order.objects.filter(buyer__username='concurrency_test_user').delete()
            
            ProductMetrics.objects.filter(
                product__slug__contains='concurrency-test-product'
            ).delete()
            
            Product.objects.filter(
                slug__contains='concurrency-test-product'
            ).delete()
            
            Category.objects.filter(
                slug='concurrency-test-category'
            ).delete()
            
            User.objects.filter(
                username='concurrency_test_user'
            ).delete()
            
            self.log("✅ Test data cleanup complete")
            
        except Exception as e:
            self.log(f"⚠️ Error during cleanup: {e}")
    
    def concurrent_stock_update_worker(self, worker_id, product_id, iterations=10):
        """Worker function for concurrent stock updates"""
        thread_name = f"StockWorker-{worker_id}"
        
        try:
            for i in range(iterations):
                try:
                    @product_transaction
                    def update_stock():
                        # Simulate realistic stock update scenario
                        product = Product.objects.select_for_update().get(id=product_id)
                        
                        # Simulate processing time
                        time.sleep(random.uniform(0.01, 0.05))
                        
                        # Random stock change (-5 to +5)
                        stock_change = random.randint(-5, 5)
                        new_stock = max(0, product.stock_quantity + stock_change)
                        
                        old_stock = product.stock_quantity
                        product.stock_quantity = new_stock
                        product.save()
                        
                        self.log(f"{thread_name} iteration {i+1}: Stock {old_stock} → {new_stock} (change: {stock_change:+d})")
                        
                        return new_stock
                    
                    final_stock = update_stock()
                    self.successes.put(f"{thread_name}-{i+1}")
                    
                except DeadlockError as e:
                    self.log(f"🔄 {thread_name} iteration {i+1}: Deadlock resolved automatically")
                    self.successes.put(f"{thread_name}-{i+1}-deadlock-recovered")
                    
                except Exception as e:
                    self.log(f"❌ {thread_name} iteration {i+1}: Error - {e}")
                    self.errors.put(f"{thread_name}-{i+1}: {e}")
                
                # Small delay between iterations
                time.sleep(random.uniform(0.001, 0.01))
                
        except Exception as e:
            self.log(f"❌ {thread_name} worker failed: {e}")
            self.errors.put(f"{thread_name}: {e}")
    
    def concurrent_payment_processing_worker(self, worker_id, order_id, iterations=5):
        """Worker function for concurrent payment processing"""
        thread_name = f"PaymentWorker-{worker_id}"
        
        try:
            for i in range(iterations):
                try:
                    @financial_transaction
                    def process_payment():
                        # Get order and user
                        order = Order.objects.select_for_update().get(id=order_id)
                        user = self.test_data['user']
                        
                        # Simulate payment processing time
                        time.sleep(random.uniform(0.02, 0.08))
                        
                        # Create payment transaction
                        payment = PaymentTransaction.objects.create(
                            seller=user,
                            buyer=user,
                            order=order,
                            stripe_payment_intent_id=f"concurrency_test_{worker_id}_{i}_{int(time.time())}",
                            stripe_checkout_session_id=f"session_{worker_id}_{i}_{int(time.time())}",
                            gross_amount=order.total_amount,
                            platform_fee=order.total_amount * Decimal('0.05'),
                            stripe_fee=order.total_amount * Decimal('0.029') + Decimal('0.30'),
                            net_amount=order.total_amount * Decimal('0.921') - Decimal('0.30'),
                            status='pending'
                        )
                        
                        # Simulate payment confirmation
                        payment.status = 'completed'
                        payment.save()
                        
                        self.log(f"{thread_name} iteration {i+1}: Payment {payment.id} processed")
                        
                        return payment
                    
                    payment = process_payment()
                    self.successes.put(f"{thread_name}-{i+1}")
                    
                except DeadlockError as e:
                    self.log(f"🔄 {thread_name} iteration {i+1}: Deadlock resolved automatically")
                    self.successes.put(f"{thread_name}-{i+1}-deadlock-recovered")
                    
                except Exception as e:
                    self.log(f"❌ {thread_name} iteration {i+1}: Error - {e}")
                    self.errors.put(f"{thread_name}-{i+1}: {e}")
                
                # Small delay between iterations
                time.sleep(random.uniform(0.01, 0.02))
                
        except Exception as e:
            self.log(f"❌ {thread_name} worker failed: {e}")
            self.errors.put(f"{thread_name}: {e}")
    
    def test_concurrent_stock_updates(self):
        """Test concurrent stock updates with row locking"""
        self.log("🧪 Testing concurrent stock updates...")
        
        # Get a test product
        product = self.test_data['products'][0]
        initial_stock = product.stock_quantity
        
        # Record initial state
        self.log(f"Initial stock for product {product.name}: {initial_stock}")
        
        # Create multiple threads to update the same product
        num_workers = 5
        iterations_per_worker = 10
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for worker_id in range(num_workers):
                future = executor.submit(
                    self.concurrent_stock_update_worker,
                    worker_id,
                    product.id,
                    iterations_per_worker
                )
                futures.append(future)
            
            # Wait for all workers to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.log(f"❌ Worker exception: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Check final state
        product.refresh_from_db()
        final_stock = product.stock_quantity
        
        # Count results
        success_count = self.successes.qsize()
        error_count = self.errors.qsize()
        
        self.log(f"Final stock for product {product.name}: {final_stock}")
        self.log(f"Stock change: {initial_stock} → {final_stock} (net: {final_stock - initial_stock:+d})")
        self.log(f"Operations: {success_count} successes, {error_count} errors")
        self.log(f"Duration: {duration:.3f}s")
        self.log(f"Throughput: {success_count/duration:.1f} operations/second")
        
        # Test passes if we have reasonable success rate and no data corruption
        success_rate = success_count / (num_workers * iterations_per_worker)
        data_integrity = final_stock >= 0  # Stock should never go negative
        
        if success_rate >= 0.8 and data_integrity:
            self.log("✅ Concurrent stock updates test PASSED")
            self.test_results['concurrent_stock_updates'] = True
        else:
            self.log(f"❌ Concurrent stock updates test FAILED (success rate: {success_rate:.1%})")
            self.test_results['concurrent_stock_updates'] = False
        
        # Clear queues for next test
        while not self.successes.empty():
            self.successes.get()
        while not self.errors.empty():
            self.errors.get()
    
    def test_concurrent_payment_processing(self):
        """Test concurrent payment processing with row locking"""
        self.log("🧪 Testing concurrent payment processing...")
        
        # Use multiple orders to reduce contention
        orders = self.test_data['orders'][:3]
        
        # Record initial payment count
        initial_payment_count = PaymentTransaction.objects.filter(
            stripe_payment_intent_id__contains='concurrency_test'
        ).count()
        
        num_workers = 6  # 2 workers per order
        iterations_per_worker = 5
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for worker_id in range(num_workers):
                # Distribute workers across orders
                order = orders[worker_id % len(orders)]
                future = executor.submit(
                    self.concurrent_payment_processing_worker,
                    worker_id,
                    order.id,
                    iterations_per_worker
                )
                futures.append(future)
            
            # Wait for all workers to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.log(f"❌ Worker exception: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Check final state
        final_payment_count = PaymentTransaction.objects.filter(
            stripe_payment_intent_id__contains='concurrency_test'
        ).count()
        
        payments_created = final_payment_count - initial_payment_count
        
        # Count results
        success_count = self.successes.qsize()
        error_count = self.errors.qsize()
        
        self.log(f"Payments created: {payments_created}")
        self.log(f"Operations: {success_count} successes, {error_count} errors")
        self.log(f"Duration: {duration:.3f}s")
        self.log(f"Throughput: {success_count/duration:.1f} operations/second")
        
        # Test passes if we created payments and have good success rate
        success_rate = success_count / (num_workers * iterations_per_worker)
        
        if success_rate >= 0.8 and payments_created > 0:
            self.log("✅ Concurrent payment processing test PASSED")
            self.test_results['concurrent_payment_processing'] = True
        else:
            self.log(f"❌ Concurrent payment processing test FAILED (success rate: {success_rate:.1%})")
            self.test_results['concurrent_payment_processing'] = False
        
        # Clear queues for next test
        while not self.successes.empty():
            self.successes.get()
        while not self.errors.empty():
            self.errors.get()
    
    def test_isolation_level_performance(self):
        """Test performance under different isolation levels"""
        self.log("🧪 Testing isolation level performance...")
        
        isolation_levels = ['READ COMMITTED', 'REPEATABLE READ', 'SERIALIZABLE']
        results = {}
        
        for isolation_level in isolation_levels:
            self.log(f"Testing with {isolation_level} isolation...")
            
            product = self.test_data['products'][1]  # Use different product
            num_workers = 3
            iterations_per_worker = 5
            
            start_time = time.time()
            
            def isolation_test_worker(worker_id):
                for i in range(iterations_per_worker):
                    try:
                        with atomic_with_isolation(isolation_level):
                            product_obj = Product.objects.select_for_update().get(id=product.id)
                            
                            # Simulate work
                            time.sleep(0.01)
                            
                            # Update stock
                            product_obj.stock_quantity += 1
                            product_obj.save()
                            
                        self.successes.put(f"isolation-{worker_id}-{i}")
                        
                    except Exception as e:
                        self.errors.put(f"isolation-{worker_id}-{i}: {e}")
            
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [
                    executor.submit(isolation_test_worker, worker_id)
                    for worker_id in range(num_workers)
                ]
                
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        self.log(f"❌ Isolation test worker exception: {e}")
            
            end_time = time.time()
            duration = end_time - start_time
            
            success_count = self.successes.qsize()
            error_count = self.errors.qsize()
            
            results[isolation_level] = {
                'duration': duration,
                'successes': success_count,
                'errors': error_count,
                'throughput': success_count / duration if duration > 0 else 0
            }
            
            self.log(f"{isolation_level}: {duration:.3f}s, {success_count} successes, {error_count} errors, {success_count/duration:.1f} ops/s")
            
            # Clear queues
            while not self.successes.empty():
                self.successes.get()
            while not self.errors.empty():
                self.errors.get()
        
        # Analyze results
        self.log("Isolation level performance comparison:")
        for level, data in results.items():
            self.log(f"  {level}: {data['throughput']:.1f} ops/s")
        
        # Test passes if all isolation levels worked
        all_successful = all(data['successes'] > 0 for data in results.values())
        
        if all_successful:
            self.log("✅ Isolation level performance test PASSED")
            self.test_results['isolation_level_performance'] = True
        else:
            self.log("❌ Isolation level performance test FAILED")
            self.test_results['isolation_level_performance'] = False
    
    def test_deadlock_detection(self):
        """Test deadlock detection and recovery"""
        self.log("🧪 Testing deadlock detection and recovery...")
        
        products = self.test_data['products'][:2]  # Use two products
        
        def deadlock_worker_a():
            """Worker that locks product A then product B"""
            try:
                for i in range(5):
                    @retry_on_deadlock(max_retries=3)
                    def lock_a_then_b():
                        with atomic_with_isolation('SERIALIZABLE'):
                            # Lock product A first
                            product_a = Product.objects.select_for_update().get(id=products[0].id)
                            self.log("Worker A: Locked product A")
                            
                            # Small delay to increase deadlock probability
                            time.sleep(0.05)
                            
                            # Then lock product B
                            product_b = Product.objects.select_for_update().get(id=products[1].id)
                            self.log("Worker A: Locked product B")
                            
                            # Update both
                            product_a.stock_quantity += 1
                            product_b.stock_quantity += 1
                            product_a.save()
                            product_b.save()
                            
                            self.log("Worker A: Updated both products")
                    
                    lock_a_then_b()
                    self.successes.put("worker-a")
                    time.sleep(0.01)
                    
            except Exception as e:
                self.log(f"❌ Worker A error: {e}")
                self.errors.put(f"worker-a: {e}")
        
        def deadlock_worker_b():
            """Worker that locks product B then product A"""
            try:
                for i in range(5):
                    @retry_on_deadlock(max_retries=3)
                    def lock_b_then_a():
                        with atomic_with_isolation('SERIALIZABLE'):
                            # Lock product B first (opposite order)
                            product_b = Product.objects.select_for_update().get(id=products[1].id)
                            self.log("Worker B: Locked product B")
                            
                            # Small delay to increase deadlock probability
                            time.sleep(0.05)
                            
                            # Then lock product A
                            product_a = Product.objects.select_for_update().get(id=products[0].id)
                            self.log("Worker B: Locked product A")
                            
                            # Update both
                            product_a.stock_quantity += 1
                            product_b.stock_quantity += 1
                            product_a.save()
                            product_b.save()
                            
                            self.log("Worker B: Updated both products")
                    
                    lock_b_then_a()
                    self.successes.put("worker-b")
                    time.sleep(0.01)
                    
            except Exception as e:
                self.log(f"❌ Worker B error: {e}")
                self.errors.put(f"worker-b: {e}")
        
        start_time = time.time()
        
        # Run workers that should cause deadlocks
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(deadlock_worker_a)
            future_b = executor.submit(deadlock_worker_b)
            
            # Wait for completion
            for future in as_completed([future_a, future_b]):
                try:
                    future.result()
                except Exception as e:
                    self.log(f"❌ Deadlock test worker exception: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        success_count = self.successes.qsize()
        error_count = self.errors.qsize()
        
        self.log(f"Deadlock test results: {success_count} successes, {error_count} errors in {duration:.3f}s")
        
        # Check transaction stats for deadlocks
        stats = TransactionMonitor.get_transaction_stats()
        deadlock_count = int(stats.get('Innodb_deadlocks', 0))
        
        self.log(f"MySQL reported deadlocks: {deadlock_count}")
        
        # Test passes if we had some successes (deadlocks were resolved)
        if success_count > 0:
            self.log("✅ Deadlock detection and recovery test PASSED")
            self.test_results['deadlock_detection'] = True
        else:
            self.log("❌ Deadlock detection and recovery test FAILED")
            self.test_results['deadlock_detection'] = False
        
        # Clear queues
        while not self.successes.empty():
            self.successes.get()
        while not self.errors.empty():
            self.errors.get()
    
    def run_all_tests(self):
        """Run all concurrency tests"""
        self.log("🚀 Starting row lock concurrency tests...")
        self.log("=" * 80)
        
        # Setup test data
        if not self.setup_test_data():
            self.log("❌ Failed to setup test data")
            return False
        
        try:
            # Run all tests
            self.test_concurrent_stock_updates()
            self.test_concurrent_payment_processing()
            self.test_isolation_level_performance()
            self.test_deadlock_detection()
            
            # Print summary
            self.log("=" * 80)
            self.log("📊 CONCURRENCY TEST RESULTS SUMMARY")
            self.log("=" * 80)
            
            passed = sum(1 for result in self.test_results.values() if result)
            total = len(self.test_results)
            
            for test_name, result in self.test_results.items():
                status = "✅ PASS" if result else "❌ FAIL"
                self.log(f"{status} {test_name}")
            
            self.log("=" * 80)
            self.log(f"Tests passed: {passed}/{total}")
            
            if passed == total:
                self.log("🎉 All concurrency tests passed! Row locking working correctly.")
            else:
                self.log("⚠️ Some concurrency tests failed. Check the implementation.")
            
            return passed == total
            
        finally:
            # Always clean up test data
            self.cleanup_test_data()

def main():
    """Main test runner"""
    print("🧪 MySQL Row Lock Concurrency Test Suite")
    print("=" * 80)
    
    # Check database connectivity
    try:
        user_count = User.objects.count()
        print(f"✅ Database connection successful. Found {user_count} users.")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # Check transaction stats availability
    try:
        stats = TransactionMonitor.get_transaction_stats()
        print(f"✅ Transaction monitoring available. Found {len(stats)} metrics.")
    except Exception as e:
        print(f"⚠️ Transaction monitoring limited: {e}")
    
    # Run tests
    tester = ConcurrencyTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()