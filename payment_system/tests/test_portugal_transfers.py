#!/usr/bin/env python3
"""
Test script to verify Portuguese connected account and test transfers.
Run this after creating the connected account to ensure everything works.
"""
import os
import sys
import django
import stripe
from decimal import Decimal

# Setup Django
django_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(django_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from payment_system.models import PaymentTransaction
from marketplace.models import Order
from payment_system.stripe_service import create_transfer_to_connected_account

User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY

def test_account_status():
    """Test the Portuguese account status and capabilities."""
    print("🔍 Testing Portuguese Account Status...")
    print("-" * 40)
    
    try:
        # Find the test user
        test_user = User.objects.get(email='portugal-seller@example.com')
        
        if not test_user.stripe_account_id:
            print("❌ Test user has no Stripe account ID")
            return False
            
        # Retrieve account from Stripe
        account = stripe.Account.retrieve(test_user.stripe_account_id)
        
        print(f"✅ Account Found: {account.id}")
        print(f"   Country: {account.country}")
        print(f"   Email: {account.email}")
        print(f"   Business Type: {account.business_type}")
        print(f"   Charges Enabled: {account.charges_enabled}")
        print(f"   Details Submitted: {account.details_submitted}")
        print(f"   Payouts Enabled: {account.payouts_enabled}")
        
        capabilities = account.capabilities
        print(f"\n🔧 Capabilities:")
        for cap, status in capabilities.items():
            print(f"   {cap}: {status}")
        
        # Check requirements
        if account.requirements.currently_due:
            print(f"\n⚠️ Requirements Currently Due:")
            for req in account.requirements.currently_due:
                print(f"   - {req}")
        else:
            print(f"\n✅ No requirements currently due")
            
        return True
        
    except User.DoesNotExist:
        print("❌ Test user not found. Run create_test_connected_account.py first.")
        return False
    except stripe.error.StripeError as e:
        print(f"❌ Stripe Error: {e}")
        return False

def test_direct_transfer():
    """Test direct Stripe transfer to Portuguese account."""
    print("\n💸 Testing Direct Stripe Transfer...")
    print("-" * 40)
    
    try:
        test_user = User.objects.get(email='portugal-seller@example.com')
        
        if not test_user.stripe_account_id:
            print("❌ No Stripe account ID found")
            return False
        
        # Create a test transfer
        transfer = stripe.Transfer.create(
            amount=1500,  # €15.00
            currency='eur',
            destination=test_user.stripe_account_id,
            description='Test transfer to Portuguese account',
            metadata={
                'test_type': 'direct_transfer',
                'user_id': str(test_user.id),
            }
        )
        
        print(f"✅ Direct Transfer Created:")
        print(f"   Transfer ID: {transfer.id}")
        print(f"   Amount: €{transfer.amount / 100:.2f}")
        print(f"   Currency: {transfer.currency.upper()}")
        print(f"   Destination: {transfer.destination}")
        print(f"   Created: {transfer.created}")
        
        return True
        
    except Exception as e:
        print(f"❌ Transfer failed: {e}")
        return False

def test_service_transfer():
    """Test transfer using our payment service."""
    print("\n🛠️ Testing Payment Service Transfer...")
    print("-" * 40)
    
    try:
        test_user = User.objects.get(email='portugal-seller@example.com')
        
        if not test_user.stripe_account_id:
            print("❌ No Stripe account ID found")
            return False
        
        # Use our service function
        result = create_transfer_to_connected_account(
            amount=2000,  # €20.00
            currency='eur',
            destination_account_id=test_user.stripe_account_id,
            transfer_group='TEST_ORDER_001',
            metadata={
                'test_type': 'service_transfer',
                'user_id': str(test_user.id),
                'test_scenario': 'portugal_account_verification'
            }
        )
        
        if result['success']:
            print(f"✅ Service Transfer Created:")
            print(f"   Transfer ID: {result['transfer_id']}")
            print(f"   Amount: €{result['amount'] / 100:.2f}")
            print(f"   Currency: {result['currency'].upper()}")
            print(f"   Destination: {result['destination']}")
            print(f"   Transfer Group: {result['transfer_group']}")
            return True
        else:
            print(f"❌ Service transfer failed: {result['errors']}")
            return False
            
    except Exception as e:
        print(f"❌ Service transfer failed: {e}")
        return False

def create_mock_payment_transaction():
    """Create a mock payment transaction for testing the full flow."""
    print("\n📦 Creating Mock Payment Transaction...")
    print("-" * 40)
    
    try:
        # Get test user (seller)
        seller = User.objects.get(email='portugal-seller@example.com')
        
        # Get or create a buyer (use admin or create test buyer)
        buyer, created = User.objects.get_or_create(
            email='test-buyer@example.com',
            defaults={
                'username': 'test_buyer',
                'first_name': 'João',
                'last_name': 'Santos',
                'is_email_verified': True,
            }
        )
        
        if created:
            buyer.set_password('TestBuyer123!')
            buyer.save()
            print(f"✅ Created test buyer: {buyer.email}")
        else:
            print(f"✅ Using existing buyer: {buyer.email}")
        
        # Create a mock order (you might need to adjust this based on your Order model)
        try:
            from marketplace.models import Order
            order, created = Order.objects.get_or_create(
                id='test-order-portugal-001',
                defaults={
                    'buyer': buyer,
                    'status': 'completed',
                    'total_amount': Decimal('25.00'),
                    'currency': 'EUR',
                }
            )
            
            if created:
                print(f"✅ Created test order: {order.id}")
            else:
                print(f"✅ Using existing order: {order.id}")
                
        except Exception as e:
            print(f"⚠️ Could not create Order (model may be different): {e}")
            # Create a minimal order object for testing
            order = type('Order', (), {
                'id': 'test-order-portugal-001',
                'buyer': buyer,
            })()
        
        # Create payment transaction
        payment_transaction = PaymentTransaction.objects.create(
            stripe_payment_intent_id='pi_test_portugal_001',
            stripe_checkout_session_id='cs_test_portugal_001',
            order=order,
            seller=seller,
            buyer=buyer,
            status='held',
            gross_amount=Decimal('25.00'),
            platform_fee=Decimal('2.50'),
            stripe_fee=Decimal('0.75'),
            net_amount=Decimal('21.75'),
            currency='EUR',
            item_count=1,
            item_names='Test Portuguese Product',
            hold_reason='standard',
            days_to_hold=30,
        )
        
        # Start the hold (this will set dates)
        payment_transaction.start_hold(reason='standard', days=30, notes='Test 30-day hold for Portugal')
        
        print(f"✅ Created PaymentTransaction:")
        print(f"   Transaction ID: {payment_transaction.id}")
        print(f"   Seller: {payment_transaction.seller.email}")
        print(f"   Buyer: {payment_transaction.buyer.email}")
        print(f"   Net Amount: €{payment_transaction.net_amount}")
        print(f"   Status: {payment_transaction.status}")
        print(f"   Days Remaining: {payment_transaction.days_remaining}")
        
        return payment_transaction
        
    except Exception as e:
        print(f"❌ Failed to create mock transaction: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None

def test_full_transfer_workflow():
    """Test the complete transfer workflow with a mock transaction."""
    print("\n🔄 Testing Full Transfer Workflow...")
    print("-" * 40)
    
    # Create mock transaction
    transaction = create_mock_payment_transaction()
    
    if not transaction:
        return False
    
    try:
        # Force the transaction to be ready for release (for testing)
        print("🎯 Forcing transaction to be ready for release...")
        transaction.planned_release_date = django.utils.timezone.now() - django.utils.timezone.timedelta(days=1)
        transaction.save()
        
        print(f"   Can be released: {transaction.can_be_released}")
        print(f"   Days remaining: {transaction.days_remaining}")
        
        if transaction.can_be_released:
            print("💸 Creating transfer via service...")
            
            # Use our transfer service
            result = create_transfer_to_connected_account(
                amount=int(transaction.net_amount * 100),  # Convert to cents
                currency=transaction.currency.lower(),
                destination_account_id=transaction.seller.stripe_account_id,
                transfer_group=f'ORDER{transaction.order.id}',
                metadata={
                    'transaction_id': str(transaction.id),
                    'order_id': str(transaction.order.id),
                    'seller_id': str(transaction.seller.id),
                    'buyer_id': str(transaction.buyer.id),
                    'test_workflow': 'true'
                }
            )
            
            if result['success']:
                # Release the payment
                transaction.release_payment(
                    released_by=transaction.seller,
                    notes=f"Test transfer created: {result['transfer_id']}"
                )
                
                print(f"✅ Full Workflow Success:")
                print(f"   Transfer ID: {result['transfer_id']}")
                print(f"   Transaction Status: {transaction.status}")
                print(f"   Released Date: {transaction.actual_release_date}")
                return True
            else:
                print(f"❌ Transfer failed: {result['errors']}")
                return False
        else:
            print("⚠️ Transaction not ready for release")
            return False
            
    except Exception as e:
        print(f"❌ Workflow test failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Run all tests."""
    print("🧪 Portuguese Connected Account Test Suite")
    print("=" * 60)
    
    if not stripe.api_key:
        print("❌ Stripe API key not configured")
        return
    
    print(f"🔑 Using Stripe API Key: {stripe.api_key[:12]}...")
    
    tests = [
        ("Account Status", test_account_status),
        ("Direct Transfer", test_direct_transfer),
        ("Service Transfer", test_service_transfer),
        ("Full Workflow", test_full_transfer_workflow),
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
        print("🎉 All tests passed! Portuguese account is ready for use.")
    else:
        print("💥 Some tests failed. Check the output above for details.")

if __name__ == '__main__':
    main()