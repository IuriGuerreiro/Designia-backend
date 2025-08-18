#!/usr/bin/env python
"""
Simple Transaction Test
======================

Basic test to verify MySQL transaction implementation is working.
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
from marketplace.models import Product, Category
from utils.transaction_utils import (
    financial_transaction, product_transaction,
    atomic_with_isolation, get_current_isolation_level,
    TransactionMonitor
)
from decimal import Decimal
import time

User = get_user_model()

def test_basic_transaction():
    """Test basic transaction functionality"""
    print("🧪 Testing basic transaction functionality...")
    
    try:
        @product_transaction
        def create_test_category():
            category = Category.objects.create(
                name=f"Test Category {int(time.time())}",
                slug=f"test-category-{int(time.time())}"
            )
            return category
        
        category = create_test_category()
        print(f"✅ Successfully created category: {category.name}")
        
        # Clean up
        category.delete()
        print("✅ Basic transaction test passed")
        return True
        
    except Exception as e:
        print(f"❌ Basic transaction test failed: {e}")
        return False

def test_isolation_level():
    """Test isolation level setting"""
    print("🧪 Testing isolation level control...")
    
    try:
        with atomic_with_isolation('SERIALIZABLE'):
            current_level = get_current_isolation_level()
            print(f"Current isolation level: {current_level}")
            
            if 'SERIALIZABLE' in current_level.upper():
                print("✅ Isolation level test passed")
                return True
            else:
                print(f"❌ Expected SERIALIZABLE, got {current_level}")
                return False
                
    except Exception as e:
        print(f"❌ Isolation level test failed: {e}")
        return False

def test_rollback():
    """Test transaction rollback on error"""
    print("🧪 Testing transaction rollback...")
    
    try:
        @product_transaction
        def failing_operation():
            # Create a category
            category = Category.objects.create(
                name=f"Rollback Test {int(time.time())}",
                slug=f"rollback-test-{int(time.time())}"
            )
            
            # Intentionally cause an error
            raise IntegrityError("Intentional error for rollback test")
        
        # This should fail and rollback
        failing_operation()
        print("❌ Expected transaction to fail and rollback")
        return False
        
    except Exception:
        # Check that no category was created (rollback worked)
        rollback_categories = Category.objects.filter(name__contains="Rollback Test")
        if rollback_categories.exists():
            rollback_categories.delete()  # Clean up any that weren't rolled back
            print("❌ Transaction rollback failed - category was created")
            return False
        else:
            print("✅ Transaction rollback test passed")
            return True

def test_transaction_stats():
    """Test transaction monitoring"""
    print("🧪 Testing transaction statistics...")
    
    try:
        stats = TransactionMonitor.get_transaction_stats()
        if stats:
            print(f"✅ Transaction stats available: {len(stats)} metrics")
            return True
        else:
            print("⚠️ No transaction stats available")
            return False
            
    except Exception as e:
        print(f"❌ Transaction stats test failed: {e}")
        return False

def main():
    """Run simple transaction tests"""
    print("🚀 Simple MySQL Transaction Test Suite")
    print("=" * 50)
    
    # Check database connectivity
    try:
        user_count = User.objects.count()
        print(f"✅ Database connection successful. Found {user_count} users.")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # Run tests
    results = []
    results.append(test_basic_transaction())
    results.append(test_isolation_level())
    results.append(test_rollback())
    results.append(test_transaction_stats())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All transaction tests passed!")
    else:
        print("⚠️ Some tests failed. Check the implementation.")

if __name__ == '__main__':
    main()