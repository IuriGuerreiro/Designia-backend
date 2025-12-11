"""
Simple management command to create basic test transaction data.

Usage:
    python manage.py create_simple_test_data
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from payment_system.models import PaymentTransaction, Payout, PayoutItem


User = get_user_model()


class Command(BaseCommand):
    help = "Create simple test transaction data for endpoint testing"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Creating Simple Test Data"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # Get or create test seller
        seller, created = User.objects.get_or_create(
            email="testseller1@designia.com",
            defaults={
                "username": "testseller1",
                "first_name": "Seller1",
                "last_name": "Test",
                "role": "seller",
                "stripe_account_id": "acct_test_seller1",
                "two_factor_enabled": True,
            },
        )
        if created:
            seller.set_password("testpass123")
            seller.save()
            self.stdout.write(f"✓ Created seller: {seller.email}")
        else:
            self.stdout.write(f"✓ Found existing seller: {seller.email}")

        # Create admin user
        admin, created = User.objects.get_or_create(
            email="admin@designia.com",
            defaults={
                "username": "admin",
                "first_name": "Admin",
                "last_name": "User",
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
                "two_factor_enabled": True,
            },
        )
        if created:
            admin.set_password("admin123")
            admin.save()
            self.stdout.write(f"✓ Created admin: {admin.email}")
        else:
            self.stdout.write(f"✓ Found existing admin: {admin.email}")

        # Create test transactions
        self.stdout.write("\n💰 Creating payment transactions...")
        transactions = []

        for i in range(10):
            amount = Decimal("100.00") + (Decimal(str(i)) * Decimal("10.00"))
            platform_fee = amount * Decimal("0.10")
            stripe_fee = amount * Decimal("0.029") + Decimal("0.30")
            net_amount = amount - platform_fee - stripe_fee

            transaction, created = PaymentTransaction.objects.get_or_create(
                stripe_payment_intent_id=f"pi_test_{i}_designia",
                defaults={
                    "seller": seller,
                    "stripe_transfer_id": f"tr_test_{i}_designia",
                    "amount": amount,
                    "currency": "usd",
                    "platform_fee": platform_fee,
                    "stripe_fee": stripe_fee,
                    "net_amount": net_amount,
                    "status": "succeeded",
                    "transfer_date": timezone.now() - timedelta(days=i),
                },
            )
            if created:
                transactions.append(transaction)

        self.stdout.write(f"   ✓ Created {len(transactions)} transactions")

        # Create test payout
        self.stdout.write("\n💸 Creating payout...")
        total_amount = sum(t.net_amount for t in transactions[:5])

        payout, created = Payout.objects.get_or_create(
            stripe_payout_id="po_test_designia_1",
            defaults={
                "seller": seller,
                "amount": total_amount,
                "currency": "usd",
                "status": "paid",
                "arrival_date": timezone.now() - timedelta(days=2),
                "created_at": timezone.now() - timedelta(days=5),
            },
        )

        if created:
            # Create payout items
            for i, transaction in enumerate(transactions[:5]):
                PayoutItem.objects.create(
                    payout=payout,
                    payment_transfer=transaction,
                    transfer_amount=transaction.net_amount,
                    transfer_currency="usd",
                    transfer_date=transaction.transfer_date,
                    order_id=f"order_{i}_test",
                    item_names=f"Test Product {i}",
                )
            self.stdout.write("   ✓ Created payout with 5 items")
        else:
            self.stdout.write("   ✓ Found existing payout")

        # Print summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("📊 Test Data Summary"))
        self.stdout.write("=" * 60)

        self.stdout.write(f"\n👤 Seller: {seller.email}")
        self.stdout.write("   Password: testpass123")
        self.stdout.write(f"   Stripe Account: {seller.stripe_account_id}\n")

        self.stdout.write(f"👤 Admin: {admin.email}")
        self.stdout.write("   Password: admin123\n")

        self.stdout.write(f"💰 Transactions: {PaymentTransaction.objects.filter(seller=seller).count()}")
        self.stdout.write(f"💸 Payouts: {Payout.objects.filter(seller=seller).count()}\n")

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("✅ Test data creation complete!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        self.stdout.write("\n🚀 Test with these endpoints:")
        self.stdout.write("   POST /payment_system/payout/ (create payout)")
        self.stdout.write("   GET  /payment_system/payouts/ (list seller payouts)")
        self.stdout.write("   GET  /payment_system/payouts/<id>/ (payout detail)")
        self.stdout.write("   GET  /payment_system/admin/payouts/ (admin list)")
        self.stdout.write("   GET  /payment_system/admin/transactions/ (admin transactions)\n")

        self.stdout.write("📝 Example cURL commands:")
        self.stdout.write("   # Login as seller")
        self.stdout.write("   curl -X POST http://localhost:8000/api/auth/login/ \\")
        self.stdout.write('        -H "Content-Type: application/json" \\')
        self.stdout.write('        -d \'{"email":"testseller1@designia.com","password":"testpass123"}\'')
        self.stdout.write("\n   # Get payouts (use token from login)")
        self.stdout.write("   curl http://localhost:8000/payment_system/payouts/ \\")
        self.stdout.write('        -H "Authorization: Bearer <token>"\n')
