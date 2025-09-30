"""
Minimal test data creation for manual endpoint testing.

Usage:
    python manage.py create_minimal_test_data
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from marketplace.models import Order, Product, OrderItem, Category
from payment_system.models import PaymentTransaction

User = get_user_model()


class Command(BaseCommand):
    help = 'Create minimal test data for manual endpoint testing'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Creating Minimal Test Data'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Get or create seller - use existing seller with stripe account or create new
        seller = User.objects.filter(
            role='seller',
            stripe_account_id__isnull=False
        ).first()

        if not seller:
            # Try to get testseller@test.com
            try:
                seller = User.objects.get(email='testseller@test.com')
                if not seller.stripe_account_id:
                    seller.stripe_account_id = 'acct_test_manual'
                    seller.save()
                self.stdout.write(f'✓ Found seller: {seller.email}')
            except User.DoesNotExist:
                seller = User.objects.create_user(
                    email='testseller@test.com',
                    username='testseller',
                    password='testpass123',
                    first_name='Test',
                    last_name='Seller',
                    role='seller',
                    stripe_account_id='acct_test_manual',
                    two_factor_enabled=True
                )
                self.stdout.write(f'✓ Created seller: {seller.email}')
        else:
            self.stdout.write(f'✓ Using existing seller: {seller.email} (Stripe: {seller.stripe_account_id})')

        # Get or create buyer (use existing if available)
        buyer = User.objects.filter(role='user').first()
        if not buyer:
            buyer = User.objects.create_user(
                email='testbuyer_manual@test.com',
                username='testbuyer_manual',
                password='testpass123',
                first_name='Test',
                last_name='Buyer',
                role='user',
                two_factor_enabled=True
            )
            self.stdout.write(f'✓ Created buyer: {buyer.email}')
        else:
            self.stdout.write(f'✓ Using existing buyer: {buyer.email}')

        # Get or create admin (use existing if available)
        admin = User.objects.filter(role='admin').first()
        if not admin:
            admin = User.objects.create_user(
                email='testadmin_manual@test.com',
                username='testadmin_manual',
                password='testpass123',
                first_name='Test',
                last_name='Admin',
                role='admin',
                is_staff=True,
                two_factor_enabled=True
            )
            self.stdout.write(f'✓ Created admin: {admin.email}')
        else:
            self.stdout.write(f'✓ Using existing admin: {admin.email}')

        # Create category and product
        category, _ = Category.objects.get_or_create(
            name='Test Category',
            defaults={'description': 'Test category for payment testing'}
        )

        product, created = Product.objects.get_or_create(
            name='Test Product',
            seller=seller,
            defaults={
                'description': 'Test product for payment endpoint testing',
                'price': Decimal('100.00'),
                'category': category,
                'stock_quantity': 100
            }
        )
        if created:
            self.stdout.write('✓ Created test product')

        # Create 5 test orders and transactions
        self.stdout.write('\n💳 Creating test orders and transactions...')
        created_count = 0

        for i in range(5):
            # Create order
            order = Order.objects.create(
                buyer=buyer,
                status='payment_confirmed',
                payment_status='paid',
                subtotal=Decimal('100.00'),
                total_amount=Decimal('100.00'),
                shipping_address={
                    "address": f"123 Test St #{i}",
                    "city": "Test City",
                    "state": "TS",
                    "zip": "12345",
                    "country": "US"
                }
            )

            # Create order item
            OrderItem.objects.create(
                order=order,
                product=product,
                seller=seller,
                quantity=1,
                unit_price=product.price,
                product_name=product.name,
                product_description=product.description
            )

            # Create payment transaction
            gross_amount = Decimal('100.00')
            platform_fee = gross_amount * Decimal('0.10')
            stripe_fee = gross_amount * Decimal('0.029') + Decimal('0.30')
            net_amount = gross_amount - platform_fee - stripe_fee

            transaction = PaymentTransaction.objects.create(
                order=order,
                seller=seller,
                buyer=buyer,
                stripe_payment_intent_id=f'pi_test_manual_{i}',
                stripe_checkout_session_id=f'cs_test_manual_{i}',
                gross_amount=gross_amount,
                platform_fee=platform_fee,
                stripe_fee=stripe_fee,
                net_amount=net_amount,
                currency='USD',
                item_count=1,
                item_names=product.name,
                status='completed',
                hold_start_date=timezone.now()
            )
            created_count += 1

        self.stdout.write(f'   ✓ Created {created_count} orders and transactions')

        # Print summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('📊 Test Data Summary'))
        self.stdout.write('=' * 60)

        self.stdout.write('\n👥 Test Users:')
        self.stdout.write(f'   Seller: testseller@test.com / testpass123')
        self.stdout.write(f'   Buyer:  testbuyer@test.com / testpass123')
        self.stdout.write(f'   Admin:  testadmin@test.com / testpass123')

        transaction_count = PaymentTransaction.objects.filter(seller=seller).count()
        self.stdout.write(f'\n💰 Data Created:')
        self.stdout.write(f'   Products: {Product.objects.filter(seller=seller).count()}')
        self.stdout.write(f'   Orders: {Order.objects.filter(buyer=buyer).count()}')
        self.stdout.write(f'   Transactions: {transaction_count}')
        self.stdout.write(f'   Total Available: ${PaymentTransaction.objects.filter(seller=seller, status="completed").aggregate(total=models.Sum("net_amount"))["total"] or 0}')

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('✅ Test Data Ready!'))
        self.stdout.write('=' * 60)

        self.stdout.write('\n🚀 Quick Test Commands:')
        self.stdout.write('   # Login as seller')
        self.stdout.write('   curl -X POST http://localhost:8000/api/auth/login/ \\')
        self.stdout.write('        -H "Content-Type: application/json" \\')
        self.stdout.write('        -d \'{"email":"testseller@test.com","password":"testpass123"}\'')
        self.stdout.write('\n   # List transactions (use token from above)')
        self.stdout.write('   curl http://localhost:8000/payment_system/payouts/ \\')
        self.stdout.write('        -H "Authorization: Bearer <your_token>"\n')


# Import for aggregation
from django.db import models