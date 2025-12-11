from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.tests.factories import UserFactory
from payment_system.models import Payout


User = get_user_model()


class AdminPayoutViewsIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = UserFactory(username="admin", email="admin@example.com", role="admin", is_staff=True)
        self.regular_user = UserFactory(username="user", email="user@example.com", role="buyer")
        self.seller_user = UserFactory(username="seller", email="seller@example.com", role="seller")

        self.payout_list_url = reverse("payment_system:admin_list_all_payouts")
        self.transaction_list_url = reverse("payment_system:admin_list_all_transactions")

    def test_admin_list_payouts_success(self):
        self.client.force_authenticate(user=self.admin_user)
        # Create some payouts
        Payout.objects.create(
            seller=self.seller_user,
            amount_decimal=Decimal("100.00"),
            amount_cents=10000,
            currency="USD",
            status="paid",
            stripe_payout_id="po_1",
        )
        Payout.objects.create(
            seller=self.seller_user,
            amount_decimal=Decimal("50.00"),
            amount_cents=5000,
            currency="USD",
            status="pending",
            stripe_payout_id="po_2",
        )

        response = self.client.get(self.payout_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["total_count"], 2)
        self.assertIn("summary", response.data)

    def test_admin_list_payouts_permission_denied(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.payout_list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_list_payouts_unauthenticated(self):
        response = self.client.get(self.payout_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_list_transactions_success(self):
        self.client.force_authenticate(user=self.admin_user)
        # Transactions would be created via factories or manually if needed for comprehensive check
        # For now, checking empty list response is valid for integration correctness
        response = self.client.get(self.transaction_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["total_count"], 0)

    def test_admin_list_transactions_permission_denied(self):
        self.client.force_authenticate(user=self.seller_user)
        response = self.client.get(self.transaction_list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
