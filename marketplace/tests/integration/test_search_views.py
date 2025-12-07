from decimal import Decimal  # Import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.tests.factories import CategoryFactory, ProductFactory, SellerFactory

User = get_user_model()


class SearchViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create user using factory
        self.user = SellerFactory(username="seller", email="seller@example.com")

        # Create categories using factories
        self.cat_electronics = CategoryFactory(name="Electronics", slug="electronics")
        self.cat_books = CategoryFactory(name="Books", slug="books")

        # Create products using factories
        self.p1 = ProductFactory(
            name="iPhone 15",
            slug="iphone-15",
            description="Latest Apple phone",
            price=Decimal("999.00"),
            seller=self.user,
            category=self.cat_electronics,
            stock_quantity=10,
            is_active=True,
            view_count=100,
        )
        self.p2 = ProductFactory(
            name="Samsung Galaxy S24",
            slug="samsung-s24",
            description="Android flagship",
            price=Decimal("899.00"),
            seller=self.user,
            category=self.cat_electronics,
            stock_quantity=5,
            is_active=True,
            view_count=50,
        )
        self.p3 = ProductFactory(
            name="Python Programming",
            slug="python-book",
            description="Learn Python",
            price=Decimal("49.00"),
            seller=self.user,
            category=self.cat_books,
            stock_quantity=20,
            is_active=True,
            view_count=10,
        )
        self.p4 = ProductFactory(
            name="Hidden Phone",
            slug="hidden-phone",
            description="Secret",
            price=Decimal("100.00"),
            seller=self.user,
            category=self.cat_electronics,
            stock_quantity=0,
            is_active=False,  # Inactive
        )

        self.search_url = reverse("marketplace:product-search")
        self.autocomplete_url = reverse("marketplace:product-autocomplete")
        self.filters_url = reverse("marketplace:product-filters")

    def test_search_basic(self):
        response = self.client.get(self.search_url, {"q": "phone"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Both p1 (iPhone 15) and p4 (Hidden Phone) contain "phone" in their name or description
        # p4 is inactive, so it should not appear.
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.p1.id))

    def test_search_category_filter(self):
        response = self.client.get(self.search_url, {"category": "electronics"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # p1 (iPhone), p2 (Samsung) are active electronics. p4 is inactive.
        self.assertEqual(len(response.data["results"]), 2)

        response = self.client.get(self.search_url, {"category": "books"})
        self.assertEqual(len(response.data["results"]), 1)  # p3

    def test_search_price_filter(self):
        response = self.client.get(self.search_url, {"price_min": 500})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)  # p1, p2

        response = self.client.get(self.search_url, {"price_max": 100})
        self.assertEqual(len(response.data["results"]), 1)  # p3

    def test_autocomplete(self):
        response = self.client.get(self.autocomplete_url, {"q": "Sam"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Samsung Galaxy S24")

    def test_filters_endpoint(self):
        # Should behave like filtering without query
        response = self.client.get(self.filters_url, {"category": "electronics"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_sorting(self):
        # Sort by price desc
        response = self.client.get(self.search_url, {"sort": "price_desc"})
        results = response.data["results"]
        self.assertEqual(results[0]["id"], str(self.p1.id))  # 999
        self.assertEqual(results[1]["id"], str(self.p2.id))  # 899
        self.assertEqual(results[2]["id"], str(self.p3.id))  # 49

        # Sort by price asc
        response = self.client.get(self.search_url, {"sort": "price_asc"})
        results = response.data["results"]
        self.assertEqual(results[0]["id"], str(self.p3.id))  # 49
