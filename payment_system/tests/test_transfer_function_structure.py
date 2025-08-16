#!/usr/bin/env python3
"""
Test script to validate the transfer function structure and imports.
This validates the consolidation of currency handling into the transfer function.
"""
import ast
import os
import sys

def test_transfer_function_integration():
    """Test that the transfer function has proper currency handler integration."""
    print("🧪 Testing Transfer Function Integration")
    print("-" * 50)
    
    # Read the views.py file
    views_path = os.path.join('payment_system', 'views.py')
    
    if not os.path.exists(views_path):
        print("❌ views.py not found")
        return False
    
    with open(views_path, 'r', encoding='utf-8') as f:
        views_content = f.read()
    
    # Check that transfer function exists
    if 'def transfer_payment_to_seller(request):' not in views_content:
        print("❌ transfer_payment_to_seller function not found")
        return False
    
    print("✅ transfer_payment_to_seller function found")
    
    # Check currency handler integration
    currency_imports = [
        'from .currency_handler import switch_currency',
        'from .currency_handler import CurrencyHandler',
    ]
    
    found_imports = []
    for import_line in currency_imports:
        if import_line in views_content:
            found_imports.append(import_line)
    
    if found_imports:
        print(f"✅ Currency handler imports found: {len(found_imports)}")
        for imp in found_imports:
            print(f"   - {imp}")
    else:
        print("❌ No currency handler imports found")
        return False
    
    # Check key currency handling components
    currency_components = [
        'CurrencyHandler.get_available_currencies_with_balance()',
        'switch_currency(',
        'currency_result[\'success\']',
        'currency_result[\'recommendation\']',
        'balance_summary',
        'currency_info',
    ]
    
    found_components = []
    for component in currency_components:
        if component in views_content:
            found_components.append(component)
    
    print(f"✅ Currency components found: {len(found_components)}/{len(currency_components)}")
    for comp in found_components:
        print(f"   - {comp}")
    
    if len(found_components) < len(currency_components) - 1:  # Allow 1 missing
        print("❌ Missing critical currency components")
        return False
    
    return True

def test_removed_utility_endpoints():
    """Test that utility endpoints were properly removed."""
    print("\n🗑️ Testing Utility Endpoints Removal")
    print("-" * 50)
    
    # Read views.py
    views_path = os.path.join('payment_system', 'views.py')
    
    with open(views_path, 'r', encoding='utf-8') as f:
        views_content = f.read()
    
    # Check that utility functions are removed
    removed_functions = [
        'def get_stripe_balance(request):',
        'def get_exchange_rates(request):',
        'def preview_currency_switch(request):',
    ]
    
    found_removed = []
    for func in removed_functions:
        if func in views_content:
            found_removed.append(func)
    
    if found_removed:
        print(f"❌ Found {len(found_removed)} utility functions that should be removed:")
        for func in found_removed:
            print(f"   - {func}")
        return False
    
    print("✅ All utility endpoints properly removed from views.py")
    
    # Check URLs
    urls_path = os.path.join('payment_system', 'urls.py')
    
    if os.path.exists(urls_path):
        with open(urls_path, 'r', encoding='utf-8') as f:
            urls_content = f.read()
        
        removed_urls = [
            'get_stripe_balance',
            'get_exchange_rates', 
            'preview_currency_switch',
        ]
        
        found_urls = []
        for url in removed_urls:
            if url in urls_content:
                found_urls.append(url)
        
        if found_urls:
            print(f"❌ Found {len(found_urls)} utility URLs that should be removed:")
            for url in found_urls:
                print(f"   - {url}")
            return False
        
        print("✅ All utility endpoints properly removed from urls.py")
    
    return True

def test_enhanced_response_structure():
    """Test that the transfer response includes comprehensive information."""
    print("\n📊 Testing Enhanced Response Structure")
    print("-" * 50)
    
    views_path = os.path.join('payment_system', 'views.py')
    
    with open(views_path, 'r', encoding='utf-8') as f:
        views_content = f.read()
    
    # Check for enhanced response fields
    response_fields = [
        'transfer_details',
        'currency_info',
        'balance_summary',
        'transaction_details',
        'current_balance_summary',
        'post_transfer_balance',
        'balance_used',
        'transfer_impact',
    ]
    
    found_fields = []
    for field in response_fields:
        if field in views_content:
            found_fields.append(field)
    
    print(f"✅ Enhanced response fields found: {len(found_fields)}/{len(response_fields)}")
    for field in found_fields:
        print(f"   - {field}")
    
    # Check for specific enhancements
    enhancements = [
        'currencies_available_before',
        'currencies_available_after', 
        'top_currencies_remaining',
        'amount_deducted',
        'conversion_needed',
        'exchange_rate',
    ]
    
    found_enhancements = []
    for enhancement in enhancements:
        if enhancement in views_content:
            found_enhancements.append(enhancement)
    
    print(f"✅ Response enhancements found: {len(found_enhancements)}/{len(enhancements)}")
    for enh in found_enhancements:
        print(f"   - {enh}")
    
    return len(found_fields) >= 4 and len(found_enhancements) >= 3

def test_error_handling_enhancements():
    """Test that error handling includes balance information."""
    print("\n⚠️ Testing Error Handling Enhancements")
    print("-" * 50)
    
    views_path = os.path.join('payment_system', 'views.py')
    
    with open(views_path, 'r', encoding='utf-8') as f:
        views_content = f.read()
    
    # Check for enhanced error responses
    error_enhancements = [
        'current_balance_summary',
        'available_currencies',
        'highest_balance_currency',
        'currencies_with_balance',
        'INSUFFICIENT_BALANCE',
    ]
    
    found_error_enhancements = []
    for enhancement in error_enhancements:
        if enhancement in views_content:
            found_error_enhancements.append(enhancement)
    
    print(f"✅ Error handling enhancements found: {len(found_error_enhancements)}/{len(error_enhancements)}")
    for enh in found_error_enhancements:
        print(f"   - {enh}")
    
    return len(found_error_enhancements) >= 3

def main():
    """Run all integration tests."""
    print("🔧 Transfer Function Consolidation Tests")
    print("=" * 60)
    
    tests = [
        ("Transfer Function Integration", test_transfer_function_integration),
        ("Utility Endpoints Removal", test_removed_utility_endpoints),
        ("Enhanced Response Structure", test_enhanced_response_structure),
        ("Error Handling Enhancements", test_error_handling_enhancements),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("🎯 Test Results Summary:")
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All consolidation tests passed! Transfer function integration complete.")
        return True
    else:
        print("💥 Some consolidation tests failed. Check implementation above.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)