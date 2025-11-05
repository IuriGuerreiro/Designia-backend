"""
Management command to create test transaction data for payment system testing.

Usage:
    python manage.py create_test_transactions
    python manage.py create_test_transactions --orders 20
    python manage.py create_test_transactions --with-payouts
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from marketplace.models import Category, Order, OrderItem, Product
from payment_system.models import PaymentTracker, PaymentTransaction, Payout, PayoutItem

User = get_user_model()


class Command(BaseCommand):
    help = "Create test transaction data for payment system endpoint testing"

    def add_arguments(self, parser):
        parser.add_argument("--orders", type=int, default=10, help="Number of orders to create (default: 10)")
        parser.add_argument(
            "--with-payouts", action="store_true", help="Create payout records for completed transactions"
        )
        parser.add_argument("--clear", action="store_true", help="Clear existing test data before creating new data")

    def handle(self, *args, **options):
        num_orders = options["orders"]
        create_payouts = options["with_payouts"]
        clear_data = options["clear"]

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Creating Test Transaction Data"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # Clear existing data if requested
        if clear_data:
            self.stdout.write("\n🗑️  Clearing existing test data...")
            PayoutItem.objects.all().delete()
            Payout.objects.all().delete()
            PaymentTracker.objects.all().delete()
            PaymentTransaction.objects.all().delete()
            OrderItem.objects.all().delete()
            Order.objects.filter(status__in=["completed", "pending_payment", "cancelled"]).delete()
            self.stdout.write(self.style.SUCCESS("   ✓ Test data cleared"))

        # Create or get test users
        self.stdout.write("\n👥 Setting up test users...")
        buyer = self._get_or_create_buyer()
        sellers = self._get_or_create_sellers(3)
        self.stdout.write(self.style.SUCCESS(f"   ✓ Created/found 1 buyer and {len(sellers)} sellers"))

        # Create test products
        self.stdout.write("\n📦 Creating test products...")
        products = self._create_test_products(sellers)
        self.stdout.write(self.style.SUCCESS(f"   ✓ Created {len(products)} products"))

        # Create orders and transactions
        self.stdout.write(f"\n💳 Creating {num_orders} test orders...")
        orders_created = self._create_test_orders(buyer, products, num_orders)
        self.stdout.write(self.style.SUCCESS(f"   ✓ Created {orders_created} orders"))

        # Create payment transactions
        self.stdout.write("\n💰 Creating payment transactions...")
        transactions = self._create_transactions()
        self.stdout.write(self.style.SUCCESS(f"   ✓ Created {len(transactions)} payment transactions"))

        # Create payouts if requested
        if create_payouts:
            self.stdout.write("\n💸 Creating payout records...")
            payouts = self._create_payouts(sellers)
            self.stdout.write(self.style.SUCCESS(f"   ✓ Created {len(payouts)} payouts"))

        # Print summary
        self._print_summary(buyer, sellers, products)

    def _get_or_create_buyer(self):
        """Create or get test buyer"""
        buyer, created = User.objects.get_or_create(
            email="testbuyer@designia.com",
            defaults={
                "username": "testbuyer",
                "first_name": "Test",
                "last_name": "Buyer",
                "role": "user",
                "two_factor_enabled": True,
            },
        )
        if created:
            buyer.set_password("testpass123")
            buyer.save()
        return buyer

    def _get_or_create_sellers(self, count):
        """Create or get test sellers"""
        sellers = []
        for i in range(1, count + 1):
            seller, created = User.objects.get_or_create(
                email=f"testseller{i}@designia.com",
                defaults={
                    "username": f"testseller{i}",
                    "first_name": f"Seller{i}",
                    "last_name": "Test",
                    "role": "seller",
                    "stripe_account_id": f"acct_test_seller{i}",
                    "two_factor_enabled": True,
                },
            )
            if created:
                seller.set_password("testpass123")
                seller.save()
            sellers.append(seller)
        return sellers

    def _create_test_products(self, sellers):
        """Create test products for sellers"""
        category, _ = Category.objects.get_or_create(
            name="Test Category", defaults={"description": "Category for test products"}
        )

        product_templates = [
            ("Premium Design Template", 49.99),
            ("UI Kit Collection", 79.99),
            ("Icon Set Bundle", 29.99),
            ("Website Template", 99.99),
            ("Mobile App UI", 149.99),
            ("Logo Design", 199.99),
            ("Brand Identity Kit", 299.99),
            ("Illustration Pack", 39.99),
        ]

        products = []
        for seller in sellers:
            for name, price in random.sample(product_templates, 3):
                product, _ = Product.objects.get_or_create(
                    name=f"{name} by {seller.username}",
                    seller=seller,
                    defaults={
                        "description": f"High-quality {name.lower()} for designers",
                        "price": Decimal(str(price)),
                        "category": category,
                        "stock_quantity": 100,
                    },
                )
                products.append(product)
        return products

    def _create_test_orders(self, buyer, products, count):
        """Create test orders with various statuses"""
        statuses = ["payment_confirmed", "pending_payment", "cancelled"]
        payment_statuses = ["paid", "pending", "failed"]

        orders_created = 0
        for i in range(count):
            # Randomly select products and quantities
            num_items = random.randint(1, 3)
            selected_products = random.sample(products, min(num_items, len(products)))

            # Create order
            status_choice = random.choice(statuses)
            payment_status = "paid" if status_choice == "payment_confirmed" else random.choice(payment_statuses)

            # Calculate total first
            total = Decimal("0.00")
            for product in selected_products:
                quantity = random.randint(1, 3)
                item_total = product.price * quantity
                total += item_total

            order = Order.objects.create(
                buyer=buyer,
                status=status_choice,
                payment_status=payment_status,
                subtotal=total,
                total_amount=total,
                shipping_address={
                    "address": f"123 Test St #{i}",
                    "city": "Test City",
                    "state": "TS",
                    "zip": "12345",
                    "country": "US",
                },
            )

            # Add order items
            for product in selected_products:
                quantity = random.randint(1, 3)

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    seller=product.seller,
                    quantity=quantity,
                    unit_price=product.price,
                    product_name=product.name,
                    product_description=product.description,
                )

            orders_created += 1

        return orders_created

    def _create_transactions(self):
        """Create payment transactions for completed orders"""
        completed_orders = Order.objects.filter(status="payment_confirmed", payment_status="paid")

        transactions = []
        for order in completed_orders:
            # Get first order item to get seller
            first_item = order.items.first()
            if not first_item:
                continue

            seller = first_item.seller

            # Calculate amounts
            total_amount = order.total_amount
            platform_fee = total_amount * Decimal("0.10")  # 10% platform fee
            stripe_fee = total_amount * Decimal("0.029") + Decimal("0.30")  # Stripe fee
            net_amount = total_amount - platform_fee - stripe_fee

            # Get item names
            item_names = ", ".join(item.product_name for item in order.items.all())

            transaction, created = PaymentTransaction.objects.get_or_create(
                order=order,
                defaults={
                    "seller": seller,
                    "buyer": order.buyer,
                    "stripe_payment_intent_id": f"pi_test_{order.id}_{random.randint(1000, 9999)}",
                    "stripe_checkout_session_id": f"cs_test_{order.id}_{random.randint(1000, 9999)}",
                    "transfer_id": f"tr_test_{order.id}",
                    "gross_amount": total_amount,
                    "currency": "USD",
                    "platform_fee": platform_fee,
                    "stripe_fee": stripe_fee,
                    "net_amount": net_amount,
                    "status": "completed",
                    "item_count": order.items.count(),
                    "item_names": item_names,
                    "hold_start_date": timezone.now() - timedelta(days=random.randint(1, 30)),
                    "payment_received_date": timezone.now() - timedelta(days=random.randint(1, 30)),
                },
            )
            if created:
                transactions.append(transaction)

        return transactions

    def _create_payouts(self, sellers):
        """Create payout records for sellers"""
        payouts = []

        for seller in sellers:
            # Get completed transactions for this seller
            transactions = PaymentTransaction.objects.filter(
                seller=seller, status="completed", payed_out=False
            ).order_by("-payment_received_date")[:5]

            if not transactions.exists():
                continue

            # Calculate payout amount
            total_amount = sum(t.net_amount for t in transactions)
            amount_cents = int(total_amount * 100)  # Convert to cents

            payout = Payout.objects.create(
                seller=seller,
                stripe_payout_id=f"po_test_{seller.id}_{random.randint(1000, 9999)}",
                amount_cents=amount_cents,
                currency="usd",
                status="paid",
                transfer_count=transactions.count(),
                arrival_date=timezone.now() - timedelta(days=random.randint(1, 5)),
            )

            # Create payout items
            for transaction in transactions:
                PayoutItem.objects.create(
                    payout=payout,
                    payment_transfer=transaction,
                    transfer_amount=transaction.net_amount,
                    transfer_currency="usd",
                    transfer_date=transaction.payment_received_date,
                    order_id=str(transaction.order.id),
                    item_names=transaction.item_names,
                )

                # Mark transaction as paid out
                transaction.payed_out = True
                transaction.save()

            payouts.append(payout)

        return payouts

    def _print_summary(self, buyer, sellers, products):
        """Print summary of created data"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("📊 Test Data Summary"))
        self.stdout.write("=" * 60)

        self.stdout.write(f"\n👤 Buyer: {buyer.email}")
        self.stdout.write("   Password: testpass123\n")

        self.stdout.write("👥 Sellers:")
        for seller in sellers:
            self.stdout.write(f"   - {seller.email} (Stripe: {seller.stripe_account_id})")
        self.stdout.write("   Password: testpass123 (for all sellers)\n")

        self.stdout.write(f"📦 Products: {len(products)} total")
        self.stdout.write(f"📋 Orders: {Order.objects.count()} total")
        self.stdout.write(f'   - Completed: {Order.objects.filter(status="completed").count()}')
        self.stdout.write(f'   - Pending: {Order.objects.filter(status="pending_payment").count()}')
        self.stdout.write(f'   - Cancelled: {Order.objects.filter(status="cancelled").count()}')

        self.stdout.write(f"\n💰 Transactions: {PaymentTransaction.objects.count()} total")
        self.stdout.write(f"💸 Payouts: {Payout.objects.count()} total\n")

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("✅ Test data creation complete!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("\n🚀 You can now test the payment system endpoints:")
        self.stdout.write("   - /payment_system/payout/ (create payout)")
        self.stdout.write("   - /payment_system/payouts/ (list payouts)")
        self.stdout.write("   - /payment_system/admin/payouts/ (admin view)")
        self.stdout.write("   - /payment_system/admin/transactions/ (admin view)\n")
