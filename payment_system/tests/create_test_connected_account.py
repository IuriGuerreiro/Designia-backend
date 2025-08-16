#!/usr/bin/env python3
"""
Script to create pre-verified test connected accounts for Portugal.
This script creates only 1 account per run to avoid duplicates.
"""
import os
import sys
import time
import django
import stripe
from django.contrib.auth import get_user_model

# Setup Django
django_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(django_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from django.conf import settings

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

User = get_user_model()

def create_portugal_connected_account():
    """
    Creates a pre-verified test connected account for Portugal with all verification
    information pre-filled.
    """
    print("🇵🇹 Creating Pre-Verified Test Connected Account for Portugal...")
    print("=" * 60)
    
    try:
        # Create the Portugal connected account
        print("🚀 Creating Stripe connected account...")
        
        portugal_account = stripe.Account.create(
            type='custom',  # Custom account gives you the most control
            country='PT',   # Portugal 
            email='portugal-seller@example.com',
            business_type='individual',
            
            # Pre-fill the individual information
            individual={
                'first_name': 'Maria',
                'last_name': 'Silva',
                'email': 'maria.silva@example.com',
                'phone': '+351210000000',
                'dob': {
                    'day': 1,
                    'month': 1,
                    'year': 1980,
                },
                'address': {
                    'line1': 'Rua Augusta 10',
                    'city': 'Lisbon',
                    'postal_code': '1100-053',
                    'country': 'PT',
                },
                'id_number': '00000000',  # Portuguese NIF (tax ID)
                'political_exposure': 'none',
                'verification': {
                    'document': {
                        'front': 'file_identity_document_success',  # Special test file ID
                    },
                },
            },
            
            # Business details
            business_profile={
                'mcc': '5734',  # Computer software store
                'url': 'https://designia-portugal-test.com',
                'name': 'Designia Portugal Test Business',
                'support_email': 'support@designia-portugal-test.com',
                'support_phone': '+351210000000',
            },
            
            # Banking information
            external_account={
                'object': 'bank_account',
                'country': 'PT',
                'currency': 'EUR',
                'account_number': 'PT50000201231234567890154',  # Test IBAN for Portugal
                'account_holder_name': 'Maria Silva',
                'account_holder_type': 'individual',
            },
            
            # Accept the Terms of Service
            tos_acceptance={
                'date': int(time.time()),
                'ip': '127.0.0.1',  # Test IP address
            },
            
            # Request the capabilities needed
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
                'sepa_debit_payments': {'requested': True},
            },
        )
        
        print(f"✅ Successfully created Stripe account: {portugal_account.id}")
        
        # Check account status
        print("\n🔍 Checking account status...")
        account = stripe.Account.retrieve(portugal_account.id)
        
        # Wait a moment for account to be processed
        time.sleep(2)
        account = stripe.Account.retrieve(portugal_account.id)
        
        # Check if the account is complete and verified
        card_payments_status = account.capabilities.get('card_payments', 'inactive')
        transfers_status = account.capabilities.get('transfers', 'inactive')
        sepa_debit_status = account.capabilities.get('sepa_debit_payments', 'inactive')
        
        is_verified = (
            card_payments_status in ['active', 'pending'] and
            transfers_status in ['active', 'pending']
        )
        
        print(f"📊 Account Details:")
        print(f"   Account ID: {account.id}")
        print(f"   Email: {account.email}")
        print(f"   Country: {account.country}")
        print(f"   Business Type: {account.business_type}")
        print(f"   Details Submitted: {account.details_submitted}")
        print(f"   Charges Enabled: {account.charges_enabled}")
        print(f"   Payouts Enabled: {account.payouts_enabled}")
        
        print(f"\n🔧 Capabilities:")
        print(f"   Card Payments: {card_payments_status}")
        print(f"   Transfers: {transfers_status}")
        print(f"   SEPA Debit: {sepa_debit_status}")
        print(f"   Is Fully Verified: {is_verified}")
        
        if account.requirements.currently_due:
            print(f"\n⚠️ Requirements Currently Due:")
            for req in account.requirements.currently_due:
                print(f"   - {req}")
        else:
            print(f"\n✅ No requirements currently due")
        
        if account.requirements.eventually_due:
            print(f"\n📋 Requirements Eventually Due:")
            for req in account.requirements.eventually_due:
                print(f"   - {req}")
        
        # Try to find or create a test user for this account
        print(f"\n👤 Setting up test user...")
        
        try:
            # Try to find existing test user
            test_user = User.objects.get(email='portugal-seller@example.com')
            print(f"   Found existing test user: {test_user.username}")
            
            # Update their Stripe account ID
            test_user.stripe_account_id = portugal_account.id
            test_user.save()
            print(f"   Updated user's Stripe account ID")
            
        except User.DoesNotExist:
            # Create new test user
            print(f"   Creating new test user...")
            test_user = User.objects.create_user(
                username='portugal_seller',
                email='portugal-seller@example.com',
                first_name='Maria',
                last_name='Silva',
                stripe_account_id=portugal_account.id,
                is_email_verified=True,
                two_factor_enabled=True,  # Enable 2FA for seller requirements
            )
            test_user.set_password('TestPassword123!')
            test_user.save()
            print(f"   Created new test user: {test_user.username}")
        
        print(f"\n🎉 SUCCESS! Test connected account created:")
        print(f"=" * 60)
        print(f"Account ID: {portugal_account.id}")
        print(f"User Email: portugal-seller@example.com")
        print(f"User Password: TestPassword123!")
        print(f"Country: Portugal (PT)")
        print(f"Currency: EUR")
        print(f"Test IBAN: PT50000201231234567890154")
        print(f"=" * 60)
        
        return {
            'success': True,
            'account_id': portugal_account.id,
            'user_email': test_user.email,
            'user_id': test_user.id,
            'account_status': {
                'charges_enabled': account.charges_enabled,
                'details_submitted': account.details_submitted,
                'payouts_enabled': account.payouts_enabled,
                'capabilities': {
                    'card_payments': card_payments_status,
                    'transfers': transfers_status,
                    'sepa_debit_payments': sepa_debit_status,
                }
            }
        }
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe API Error: {str(e)}")
        return {'success': False, 'error': str(e)}
    
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {'success': False, 'error': str(e)}

def test_transfer_capability(account_id):
    """
    Test the transfer capability by creating a small test transfer.
    """
    print(f"\n🧪 Testing transfer capability for account {account_id}...")
    
    try:
        # Create a small test transfer (10 EUR = 1000 cents)
        test_transfer = stripe.Transfer.create(
            amount=1000,  # 10 EUR in cents
            currency='eur',
            destination=account_id,
            description='Test transfer for Portugal connected account',
        )
        
        print(f"✅ Test transfer created successfully!")
        print(f"   Transfer ID: {test_transfer.id}")
        print(f"   Amount: €{test_transfer.amount / 100:.2f}")
        print(f"   Currency: {test_transfer.currency.upper()}")
        print(f"   Status: {test_transfer.object}")
        
        return True
        
    except stripe.error.StripeError as e:
        print(f"❌ Transfer test failed: {str(e)}")
        return False

def check_existing_accounts():
    """
    Check if we already have test accounts to prevent duplicates.
    """
    print("🔍 Checking for existing test accounts...")
    
    try:
        # Check if we already have a user with Portugal test account
        existing_user = User.objects.filter(
            email='portugal-seller@example.com'
        ).first()
        
        if existing_user and existing_user.stripe_account_id:
            print(f"⚠️  Found existing test account:")
            print(f"   User: {existing_user.username} ({existing_user.email})")
            print(f"   Stripe Account: {existing_user.stripe_account_id}")
            
            # Verify the account still exists in Stripe
            try:
                account = stripe.Account.retrieve(existing_user.stripe_account_id)
                print(f"   Account Status: Active")
                return existing_user.stripe_account_id
            except stripe.error.StripeError:
                print(f"   Account Status: Not found in Stripe (will create new)")
                existing_user.stripe_account_id = None
                existing_user.save()
                return None
        
        return None
        
    except Exception as e:
        print(f"⚠️  Error checking existing accounts: {e}")
        return None

def main():
    """
    Main function to create test connected account.
    """
    print("🚀 Designia Portugal Test Connected Account Creator")
    print("=" * 60)
    
    if not stripe.api_key:
        print("❌ Error: Stripe API key not found!")
        print("   Please ensure STRIPE_SECRET_KEY is set in Django settings.")
        return
    
    print(f"🔑 Using Stripe API Key: {stripe.api_key[:12]}...")
    
    # Check for existing accounts first
    existing_account_id = check_existing_accounts()
    
    if existing_account_id:
        print(f"\n✋ Account already exists! Skipping creation.")
        print(f"   To create a new account, delete the existing user first.")
        
        # Still test transfer capability
        test_transfer_capability(existing_account_id)
        return
    
    # Create new account
    result = create_portugal_connected_account()
    
    if result['success']:
        # Test transfer capability
        test_transfer_capability(result['account_id'])
        
        print(f"\n📋 Quick Setup Guide:")
        print(f"1. Login to Django admin or your app with:")
        print(f"   Email: portugal-seller@example.com")
        print(f"   Password: TestPassword123!")
        print(f"2. The account is pre-verified for testing")
        print(f"3. You can now test transfers to this account")
        print(f"4. Account supports EUR currency and SEPA payments")
        
    else:
        print(f"\n💥 Failed to create test account: {result['error']}")

if __name__ == '__main__':
    main()