"""
Django management command to create a pre-verified Portuguese connected account for testing.
Usage: python manage.py create_test_portugal_account
"""
import time
import stripe
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a pre-verified Portuguese Stripe connected account for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force creation even if account already exists',
        )
        parser.add_argument(
            '--test-transfer',
            action='store_true',
            help='Test transfer capability after creating account',
        )

    def handle(self, *args, **options):
        # Configure Stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        if not stripe.api_key:
            self.stdout.write(
                self.style.ERROR('❌ Error: Stripe API key not found!')
            )
            return

        self.stdout.write("🇵🇹 Creating Pre-Verified Portuguese Connected Account...")
        self.stdout.write("=" * 60)

        # Check for existing account
        if not options['force']:
            existing_user = User.objects.filter(email='portugal-seller@example.com').first()
            if existing_user and existing_user.stripe_account_id:
                try:
                    # Verify account exists in Stripe
                    stripe.Account.retrieve(existing_user.stripe_account_id)
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  Account already exists: {existing_user.stripe_account_id}')
                    )
                    self.stdout.write('Use --force to create a new one')
                    return
                except stripe.error.StripeError:
                    # Account doesn't exist in Stripe, continue with creation
                    pass

        try:
            # Create the Portuguese connected account
            self.stdout.write("🚀 Creating Stripe connected account...")
            
            portugal_account = stripe.Account.create(
                type='custom',
                country='PT',
                email='portugal-seller@example.com',
                business_type='individual',
                
                individual={
                    'first_name': 'Maria',
                    'last_name': 'Silva',
                    'email': 'maria.silva@example.com',
                    'phone': '+351210000000',
                    'dob': {'day': 1, 'month': 1, 'year': 1980},
                    'address': {
                        'line1': 'Rua Augusta 10',
                        'city': 'Lisbon',
                        'postal_code': '1100-053',
                        'country': 'PT',
                    },
                    'id_number': '00000000',
                    'political_exposure': 'none',
                    'verification': {
                        'document': {'front': 'file_identity_document_success'}
                    },
                },
                
                business_profile={
                    'mcc': '5734',
                    'url': 'https://designia-portugal-test.com',
                    'name': 'Designia Portugal Test Business',
                    'support_email': 'support@designia-portugal-test.com',
                    'support_phone': '+351210000000',
                },
                
                external_account={
                    'object': 'bank_account',
                    'country': 'PT',
                    'currency': 'EUR',
                    'account_number': 'PT50000201231234567890154',
                    'account_holder_name': 'Maria Silva',
                    'account_holder_type': 'individual',
                },
                
                tos_acceptance={
                    'date': int(time.time()),
                    'ip': '127.0.0.1',
                },
                
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True},
                    'sepa_debit_payments': {'requested': True},
                },
            )

            self.stdout.write(
                self.style.SUCCESS(f"✅ Created Stripe account: {portugal_account.id}")
            )

            # Wait and check account status
            time.sleep(2)
            account = stripe.Account.retrieve(portugal_account.id)

            # Create or update Django user
            try:
                test_user = User.objects.get(email='portugal-seller@example.com')
                test_user.stripe_account_id = portugal_account.id
                test_user.save()
                self.stdout.write("📝 Updated existing user's Stripe account ID")
            except User.DoesNotExist:
                test_user = User.objects.create_user(
                    username='portugal_seller',
                    email='portugal-seller@example.com',
                    first_name='Maria',
                    last_name='Silva',
                    stripe_account_id=portugal_account.id,
                    is_email_verified=True,
                    two_factor_enabled=True,
                )
                test_user.set_password('TestPassword123!')
                test_user.save()
                self.stdout.write("👤 Created new test user")

            # Display account details
            self.stdout.write("\n📊 Account Details:")
            self.stdout.write(f"   Account ID: {account.id}")
            self.stdout.write(f"   Country: {account.country}")
            self.stdout.write(f"   Charges Enabled: {account.charges_enabled}")
            self.stdout.write(f"   Details Submitted: {account.details_submitted}")

            capabilities = account.capabilities
            self.stdout.write(f"\n🔧 Capabilities:")
            self.stdout.write(f"   Card Payments: {capabilities.get('card_payments', 'inactive')}")
            self.stdout.write(f"   Transfers: {capabilities.get('transfers', 'inactive')}")
            self.stdout.write(f"   SEPA Debit: {capabilities.get('sepa_debit_payments', 'inactive')}")

            # Test transfer if requested
            if options['test_transfer']:
                self.stdout.write("\n🧪 Testing transfer capability...")
                try:
                    test_transfer = stripe.Transfer.create(
                        amount=1000,  # €10.00
                        currency='eur',
                        destination=portugal_account.id,
                        description='Test transfer for Portuguese account',
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ Test transfer successful: {test_transfer.id}")
                    )
                except stripe.error.StripeError as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Transfer test failed: {str(e)}")
                    )

            # Success summary
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(self.style.SUCCESS("🎉 SUCCESS! Test account created:"))
            self.stdout.write(f"Account ID: {portugal_account.id}")
            self.stdout.write(f"Login Email: portugal-seller@example.com")
            self.stdout.write(f"Password: TestPassword123!")
            self.stdout.write(f"Country: Portugal (PT)")
            self.stdout.write(f"Currency: EUR")
            self.stdout.write("=" * 60)

        except stripe.error.StripeError as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Stripe API Error: {str(e)}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Unexpected Error: {str(e)}")
            )