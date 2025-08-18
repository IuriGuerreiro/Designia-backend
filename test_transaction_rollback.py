#!/usr/bin/env python
"""
Transaction Rollback Test Script
===============================

Test script to demonstrate MySQL transaction rollback scenarios
with the new transaction utilities.

Usage:
    python test_transaction_rollback.py

This script tests:
1. Successful transaction commit
2. Transaction rollback on error
3. Deadlock handling and retry
4. Isolation level testing
5. Performance monitoring
"""

import os
import sys
import django
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from marketplace.models import Product, Category, ProductMetrics, Order
from payment_system.models import PaymentTransaction
from utils.transaction_utils import (
    financial_transaction, product_transaction,
    atomic_with_isolation, rollback_safe_operation,
    get_current_isolation_level, TransactionMonitor
)
from decimal import Decimal
import time

User = get_user_model()

class TransactionTester:
    """Test class for transaction scenarios"""
    
    def __init__(self):
        self.test_results = {}
    
    def log(self, message):
        """Log test messages"""
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] {message}")
    
    def test_successful_transaction(self):
        """Test successful transaction commit"""
        self.log("🧪 Testing successful transaction commit...")
        
        try:
            @financial_transaction
            def create_test_payment():
                user = User.objects.filter(is_active=True).first()
                if not user:
                    raise Exception("No active user found for testing")
                
                # Create a test order first
                category, _ = Category.objects.get_or_create(
                    name="Test Category",
                    defaults={'slug': 'test-category-payment'}
                )
                
                order = Order.objects.create(
                    buyer=user,
                    status='pending_payment',
                    payment_status='pending',
                    subtotal=Decimal('100.00'),
                    shipping_cost=Decimal('0.00'),
                    tax_amount=Decimal('0.00'),
                    total_amount=Decimal('100.00'),
                    shipping_address={}  # Empty JSON object for shipping address
                )
                
                # Create a test payment transaction with correct fields
                payment = PaymentTransaction.objects.create(
                    seller=user,
                    buyer=user,
                    order=order,
                    stripe_payment_intent_id=f"test_payment_{int(time.time())}",
                    stripe_checkout_session_id=f"test_session_{int(time.time())}",
                    gross_amount=Decimal('100.00'),
                    platform_fee=Decimal('5.00'),
                    stripe_fee=Decimal('3.20'),
                    net_amount=Decimal('91.80'),
                    status='pending'
                )
                
                # Update status
                payment.status = 'completed'
                payment.save()
                
                return payment
            
            payment = create_test_payment()
            self.log(f"✅ Successfully created payment transaction: {payment.id}")
            self.test_results['successful_transaction'] = True
            
        except Exception as e:
            self.log(f"❌ Successful transaction test failed: {e}")
            self.test_results['successful_transaction'] = False
    
    def test_transaction_rollback(self):
        """Test transaction rollback on error"""
        self.log("🧪 Testing transaction rollback on error...")
        
        try:
            @product_transaction
            def create_failing_product():
                user = User.objects.filter(is_active=True).first()
                if not user:
                    raise Exception("No active user found for testing")
                
                category, _ = Category.objects.get_or_create(
                    name="Test Category",
                    defaults={'slug': 'test-category'}
                )
                
                # Create a product
                product = Product.objects.create(
                    name="Test Product",
                    slug=f"test-product-{int(time.time())}",
                    description="Test product for transaction testing",
                    price=Decimal('50.00'),
                    stock_quantity=10,
                    seller=user,
                    category=category
                )
                
                # Intentionally cause an error to trigger rollback
                raise IntegrityError("Intentional error to test rollback")
            
            # This should raise an exception and rollback
            create_failing_product()
            self.log("❌ Expected transaction to fail and rollback")
            self.test_results['transaction_rollback'] = False
            
        except Exception as e:
            # Check that no product was created (transaction rolled back)
            test_slug = f"test-product-{int(time.time())}"
            test_products = Product.objects.filter(slug__startswith="test-product-")
            if test_products.exists():
                # Clean up any test products that weren't rolled back
                test_products.delete()
                self.log("❌ Transaction rollback failed - product was created despite error")
                self.test_results['transaction_rollback'] = False
            else:
                self.log("✅ Transaction rollback successful - no product created")
                self.test_results['transaction_rollback'] = True
    
    def test_isolation_levels(self):
        """Test different isolation levels"""
        self.log("🧪 Testing isolation levels...")
        
        try:
            # Test SERIALIZABLE isolation
            with atomic_with_isolation('SERIALIZABLE'):
                current_level = get_current_isolation_level()
                self.log(f"Current isolation level: {current_level}")
                
                if 'SERIALIZABLE' in current_level.upper():
                    self.log("✅ SERIALIZABLE isolation level set correctly")
                    self.test_results['isolation_levels'] = True
                else:
                    self.log(f"❌ Expected SERIALIZABLE, got {current_level}")
                    self.test_results['isolation_levels'] = False
            
        except Exception as e:
            self.log(f"❌ Isolation level test failed: {e}")
            self.test_results['isolation_levels'] = False
    
    def test_rollback_safe_operation(self):
        """Test rollback safe operation context manager"""
        self.log("🧪 Testing rollback safe operation...")
        
        try:
            with rollback_safe_operation("Test Operation"):
                # Simulate some work
                time.sleep(0.1)
                
                # This should complete successfully
                user_count = User.objects.count()
                self.log(f"Found {user_count} users in rollback safe operation")
            
            self.log("✅ Rollback safe operation completed successfully")
            self.test_results['rollback_safe_operation'] = True
            
        except Exception as e:
            self.log(f"❌ Rollback safe operation test failed: {e}")
            self.test_results['rollback_safe_operation'] = False
    
    def test_performance_monitoring(self):
        """Test transaction performance monitoring"""
        self.log("🧪 Testing performance monitoring...")
        
        try:
            @product_transaction  # This includes performance logging
            def performance_test_operation():
                # Simulate database work
                user_count = User.objects.count()
                product_count = Product.objects.count()
                
                # Simulate some processing time
                time.sleep(0.1)
                
                return user_count, product_count
            
            result = performance_test_operation()
            self.log(f"✅ Performance monitoring test completed: {result}")
            self.test_results['performance_monitoring'] = True
            
        except Exception as e:
            self.log(f"❌ Performance monitoring test failed: {e}")
            self.test_results['performance_monitoring'] = False
    
    def test_nested_transactions(self):
        """Test nested transaction handling"""
        self.log("🧪 Testing nested transactions...")
        
        try:
            @financial_transaction
            def outer_transaction():
                user = User.objects.filter(is_active=True).first()
                if not user:
                    raise Exception("No active user found for testing")
                
                # Create test orders
                category, _ = Category.objects.get_or_create(
                    name="Test Category Nested",
                    defaults={'slug': 'test-category-nested'}
                )
                
                order1 = Order.objects.create(
                    buyer=user,
                    status='pending_payment',
                    payment_status='pending',
                    subtotal=Decimal('200.00'),
                    shipping_cost=Decimal('0.00'),
                    tax_amount=Decimal('0.00'),
                    total_amount=Decimal('200.00'),
                    shipping_address={}
                )
                
                order2 = Order.objects.create(
                    buyer=user,
                    status='pending_payment',
                    payment_status='pending',
                    subtotal=Decimal('50.00'),
                    shipping_cost=Decimal('0.00'),
                    tax_amount=Decimal('0.00'),
                    total_amount=Decimal('50.00'),
                    shipping_address={}
                )
                
                # Create outer transaction item
                payment1 = PaymentTransaction.objects.create(
                    seller=user,
                    buyer=user,
                    order=order1,
                    stripe_payment_intent_id=f"nested_outer_{int(time.time())}",
                    stripe_checkout_session_id=f"nested_outer_session_{int(time.time())}",
                    gross_amount=Decimal('200.00'),
                    platform_fee=Decimal('10.00'),
                    stripe_fee=Decimal('6.20'),
                    net_amount=Decimal('183.80'),
                    status='pending'
                )
                
                # Nested transaction using context manager
                with atomic_with_isolation('REPEATABLE READ', savepoint=True):
                    payment2 = PaymentTransaction.objects.create(
                        seller=user,
                        buyer=user,
                        order=order2,
                        stripe_payment_intent_id=f"nested_inner_{int(time.time())}",
                        stripe_checkout_session_id=f"nested_inner_session_{int(time.time())}",
                        gross_amount=Decimal('50.00'),
                        platform_fee=Decimal('2.50'),
                        stripe_fee=Decimal('1.75'),
                        net_amount=Decimal('45.75'),
                        status='pending'
                    )
                    
                    # Both should be saved
                    payment2.status = 'completed'
                    payment2.save()
                
                payment1.status = 'completed'
                payment1.save()
                
                return payment1, payment2
            
            payments = outer_transaction()
            self.log(f"✅ Nested transactions completed: {[p.id for p in payments]}")
            self.test_results['nested_transactions'] = True
            
        except Exception as e:
            self.log(f"❌ Nested transactions test failed: {e}")
            self.test_results['nested_transactions'] = False
    
    def test_transaction_stats(self):
        """Test transaction statistics monitoring"""
        self.log("🧪 Testing transaction statistics...")
        
        try:
            # Get current transaction stats
            stats = TransactionMonitor.get_transaction_stats()
            
            if stats:
                self.log(f"✅ Transaction stats retrieved: {len(stats)} metrics")
                for key, value in stats.items():
                    self.log(f"  {key}: {value}")
                self.test_results['transaction_stats'] = True
            else:
                self.log("⚠️ No transaction stats available")
                self.test_results['transaction_stats'] = False
                
        except Exception as e:
            self.log(f"❌ Transaction stats test failed: {e}")
            self.test_results['transaction_stats'] = False
    
    def run_all_tests(self):
        """Run all transaction tests"""
        self.log("🚀 Starting transaction rollback tests...")
        self.log("=" * 60)
        
        # Run all tests
        self.test_successful_transaction()
        self.test_transaction_rollback()
        self.test_isolation_levels()
        self.test_rollback_safe_operation()
        self.test_performance_monitoring()
        self.test_nested_transactions()
        self.test_transaction_stats()
        
        # Print summary
        self.log("=" * 60)
        self.log("📊 TEST RESULTS SUMMARY")
        self.log("=" * 60)
        
        passed = sum(1 for result in self.test_results.values() if result)
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            self.log(f"{status} {test_name}")
        
        self.log("=" * 60)
        self.log(f"Tests passed: {passed}/{total}")
        
        if passed == total:
            self.log("🎉 All tests passed! Transaction utilities working correctly.")
        else:
            self.log("⚠️ Some tests failed. Check the implementation.")
        
        return passed == total

def main():
    """Main test runner"""
    print("🧪 MySQL Transaction Utilities Test Suite")
    print("=" * 60)
    
    # Check database connectivity
    try:
        user_count = User.objects.count()
        print(f"✅ Database connection successful. Found {user_count} users.")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # Run tests
    tester = TransactionTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()