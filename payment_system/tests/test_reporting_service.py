"""
Tests for ReportingService

Phase 1 SOLID Refactoring - Service Layer Extraction
Tests the reporting service which extracts aggregation logic from AdminPayoutViews
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from marketplace.models import Order
from payment_system.models import PaymentTransaction, Payout
from payment_system.services.reporting_service import ReportingService


User = get_user_model()


class ReportingServicePayoutsSummaryTest(TestCase):
    def setUp(self):
        # Create test users
        self.seller1 = User.objects.create_user(
            username="seller1", email="seller1@example.com", password="password", role="seller"
        )
        self.seller2 = User.objects.create_user(
            username="seller2", email="seller2@example.com", password="password", role="seller"
        )

    def test_get_payouts_summary_no_filters(self):
        """Test getting all payouts without filters"""
        # Create payouts
        Payout.objects.create(
            seller=self.seller1, amount_decimal=Decimal("100.00"), status="paid", total_fees=Decimal("10.00")
        )
        Payout.objects.create(
            seller=self.seller2, amount_decimal=Decimal("200.00"), status="pending", total_fees=Decimal("20.00")
        )

        result = ReportingService.get_payouts_summary({})

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["summary_stats"]["total_amount"], Decimal("300.00"))
        self.assertEqual(result["summary_stats"]["average_amount"], Decimal("150.00"))
        self.assertEqual(result["summary_stats"]["total_fees"], Decimal("30.00"))
        self.assertEqual(result["status_breakdown"]["paid"], 1)
        self.assertEqual(result["status_breakdown"]["pending"], 1)

    def test_get_payouts_summary_filter_by_status(self):
        """Test filtering payouts by status"""
        Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("100.00"), status="paid")
        Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("200.00"), status="pending")
        Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("300.00"), status="failed")

        result = ReportingService.get_payouts_summary({"status": "paid"})

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["summary_stats"]["total_amount"], Decimal("100.00"))

    def test_get_payouts_summary_filter_by_seller(self):
        """Test filtering payouts by seller ID"""
        Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("100.00"), status="paid")
        Payout.objects.create(seller=self.seller2, amount_decimal=Decimal("200.00"), status="paid")

        result = ReportingService.get_payouts_summary({"seller_id": str(self.seller1.id)})

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["summary_stats"]["total_amount"], Decimal("100.00"))

    def test_get_payouts_summary_filter_by_date_range(self):
        """Test filtering payouts by date range"""
        # Create payouts with specific dates
        payout1 = Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("100.00"), status="paid")
        payout1.created_at = timezone.datetime(2025, 1, 1, tzinfo=timezone.utc)
        payout1.save()

        payout2 = Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("200.00"), status="paid")
        payout2.created_at = timezone.datetime(2025, 2, 1, tzinfo=timezone.utc)
        payout2.save()

        # Filter for January 2025 only
        result = ReportingService.get_payouts_summary({"from_date": "2025-01-01", "to_date": "2025-01-31"})

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["summary_stats"]["total_amount"], Decimal("100.00"))

    def test_get_payouts_summary_search_by_username(self):
        """Test searching payouts by seller username"""
        Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("100.00"), status="paid")
        Payout.objects.create(seller=self.seller2, amount_decimal=Decimal("200.00"), status="paid")

        result = ReportingService.get_payouts_summary({"search": "seller1"})

        self.assertEqual(result["total_count"], 1)
        payouts_list = list(result["payouts_queryset"])
        self.assertEqual(payouts_list[0].seller, self.seller1)

    def test_get_payouts_summary_search_by_email(self):
        """Test searching payouts by seller email"""
        Payout.objects.create(seller=self.seller1, amount_decimal=Decimal("100.00"), status="paid")
        Payout.objects.create(seller=self.seller2, amount_decimal=Decimal("200.00"), status="paid")

        result = ReportingService.get_payouts_summary({"search": "seller2@example.com"})

        self.assertEqual(result["total_count"], 1)
        payouts_list = list(result["payouts_queryset"])
        self.assertEqual(payouts_list[0].seller, self.seller2)

    def test_get_payouts_summary_empty_result(self):
        """Test when no payouts match the filters"""
        result = ReportingService.get_payouts_summary({"status": "paid"})

        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["summary_stats"]["total_amount"], Decimal("0.00"))
        self.assertEqual(result["summary_stats"]["average_amount"], Decimal("0.00"))


class ReportingServiceTransactionReportTest(TestCase):
    def setUp(self):
        # Create test users
        self.seller1 = User.objects.create_user(
            username="seller1", email="seller1@example.com", password="password", role="seller"
        )
        self.buyer1 = User.objects.create_user(
            username="buyer1", email="buyer1@example.com", password="password", role="customer"
        )
        self.buyer2 = User.objects.create_user(
            username="buyer2", email="buyer2@example.com", password="password", role="customer"
        )

        # Create orders for transactions
        self.order1 = Order.objects.create(
            buyer=self.buyer1, total_amount=Decimal("100.00"), subtotal=Decimal("100.00"), shipping_address={}
        )
        self.order2 = Order.objects.create(
            buyer=self.buyer2, total_amount=Decimal("200.00"), subtotal=Decimal("200.00"), shipping_address={}
        )

    def test_get_transaction_report_no_filters(self):
        """Test getting all transactions without filters"""
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="held",
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            stripe_fee=Decimal("5.00"),
            net_amount=Decimal("85.00"),
            stripe_payment_intent_id="pi_1",
        )
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer2,
            order=self.order2,
            status="completed",
            gross_amount=Decimal("200.00"),
            platform_fee=Decimal("20.00"),
            stripe_fee=Decimal("10.00"),
            net_amount=Decimal("170.00"),
            stripe_payment_intent_id="pi_2",
        )

        result = ReportingService.get_transaction_report({})

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["summary_stats"]["total_gross"], Decimal("300.00"))
        self.assertEqual(result["summary_stats"]["total_net"], Decimal("255.00"))
        self.assertEqual(result["summary_stats"]["total_platform_fees"], Decimal("30.00"))
        self.assertEqual(result["summary_stats"]["total_stripe_fees"], Decimal("15.00"))
        self.assertEqual(result["status_breakdown"]["held"], 1)
        self.assertEqual(result["status_breakdown"]["completed"], 1)

    def test_get_transaction_report_filter_by_status(self):
        """Test filtering transactions by status"""
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="held",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("85.00"),
            stripe_payment_intent_id="pi_1",
        )
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("200.00"),
            net_amount=Decimal("170.00"),
            stripe_payment_intent_id="pi_2",
        )

        result = ReportingService.get_transaction_report({"status": "held"})

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["summary_stats"]["total_gross"], Decimal("100.00"))

    def test_get_transaction_report_filter_by_seller(self):
        """Test filtering transactions by seller ID"""
        seller2 = User.objects.create_user(
            username="seller2", email="seller2@example.com", password="password", role="seller"
        )

        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("85.00"),
            stripe_payment_intent_id="pi_1",
        )
        PaymentTransaction.objects.create(
            seller=seller2,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("200.00"),
            net_amount=Decimal("170.00"),
            stripe_payment_intent_id="pi_2",
        )

        result = ReportingService.get_transaction_report({"seller_id": str(self.seller1.id)})

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["summary_stats"]["total_gross"], Decimal("100.00"))

    def test_get_transaction_report_filter_by_buyer(self):
        """Test filtering transactions by buyer ID"""
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("85.00"),
            stripe_payment_intent_id="pi_1",
        )
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer2,
            order=self.order2,
            status="completed",
            gross_amount=Decimal("200.00"),
            net_amount=Decimal("170.00"),
            stripe_payment_intent_id="pi_2",
        )

        result = ReportingService.get_transaction_report({"buyer_id": str(self.buyer1.id)})

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["summary_stats"]["total_gross"], Decimal("100.00"))

    def test_get_transaction_report_search_by_seller_username(self):
        """Test searching transactions by seller username"""
        seller2 = User.objects.create_user(
            username="alice", email="alice@example.com", password="password", role="seller"
        )

        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("85.00"),
            stripe_payment_intent_id="pi_1",
        )
        PaymentTransaction.objects.create(
            seller=seller2,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("200.00"),
            net_amount=Decimal("170.00"),
            stripe_payment_intent_id="pi_2",
        )

        result = ReportingService.get_transaction_report({"search": "alice"})

        self.assertEqual(result["total_count"], 1)
        transactions_list = list(result["transactions_queryset"])
        self.assertEqual(transactions_list[0].seller, seller2)

    def test_get_transaction_report_empty_result(self):
        """Test when no transactions match the filters"""
        result = ReportingService.get_transaction_report({"status": "completed"})

        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["summary_stats"]["total_gross"], Decimal("0.00"))
        self.assertEqual(result["summary_stats"]["total_net"], Decimal("0.00"))

    def test_get_transaction_report_average_calculation(self):
        """Test that average transaction amount is calculated correctly"""
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("85.00"),
            stripe_payment_intent_id="pi_1",
        )
        PaymentTransaction.objects.create(
            seller=self.seller1,
            buyer=self.buyer1,
            order=self.order1,
            status="completed",
            gross_amount=Decimal("200.00"),
            net_amount=Decimal("170.00"),
            stripe_payment_intent_id="pi_2",
        )

        result = ReportingService.get_transaction_report({})

        self.assertEqual(result["summary_stats"]["average_transaction"], Decimal("150.00"))
