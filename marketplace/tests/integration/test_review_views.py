from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import ProductReview
from marketplace.tests.factories import (
    CategoryFactory,
    OrderFactory,
    OrderItemFactory,
    ProductFactory,
    ProductReviewFactory,
    SellerFactory,
    UserFactory,
)


User = get_user_model()


class ReviewViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users using factories
        self.user = UserFactory(username="user", email="user@example.com")
        self.seller = SellerFactory(username="seller", email="seller@example.com")
        self.other_user = UserFactory(username="other", email="other@example.com")

        # Create category using factory
        self.category = CategoryFactory()

        # Create product using factory
        self.product = ProductFactory(seller=self.seller, category=self.category, stock_quantity=10)

        # Create verified order for user using factories
        # Ensure OrderFactory and OrderItemFactory create necessary fields
        self.order = OrderFactory(buyer=self.user, status="delivered")
        OrderItemFactory(
            order=self.order,
            product=self.product,
            seller=self.seller,
            quantity=1,
            unit_price=self.product.price,
            total_price=self.product.price,
        )

        self.review_list_url = reverse("marketplace:review-list")

    def test_create_review_success(self):
        self.client.force_authenticate(user=self.user)
        data = {"product_id": str(self.product.id), "rating": 5, "title": "Great!", "comment": "Loved it."}
        response = self.client.post(self.review_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ProductReview.objects.count(), 1)
        self.assertTrue(response.data["is_verified_purchase"])

    def test_create_duplicate_review_fail(self):
        self.client.force_authenticate(user=self.user)
        # Create first review using factory
        ProductReviewFactory(product=self.product, reviewer=self.user, title="First", comment="First")

        data = {"product_id": str(self.product.id), "rating": 4, "title": "Second", "comment": "Second"}
        response = self.client.post(self.review_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already reviewed", response.data["detail"])

    def test_update_review_success(self):
        self.client.force_authenticate(user=self.user)
        # Create review using factory
        review = ProductReviewFactory(product=self.product, reviewer=self.user, rating=5, title="Old", comment="Old")

        url = reverse("marketplace:review-detail", args=[review.id])
        data = {"rating": 4, "title": "New"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        review.refresh_from_db()
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.title, "New")

    def test_update_others_review_fail(self):
        self.client.force_authenticate(user=self.other_user)
        # Create review using factory
        review = ProductReviewFactory(
            product=self.product, reviewer=self.user, rating=5, title="User's", comment="User's"
        )

        url = reverse("marketplace:review-detail", args=[review.id])
        data = {"rating": 1}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_review_success(self):
        self.client.force_authenticate(user=self.user)
        # Create review using factory
        review = ProductReviewFactory(product=self.product, reviewer=self.user, rating=5, title="Del", comment="Del")

        url = reverse("marketplace:review-detail", args=[review.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        review.refresh_from_db()
        self.assertFalse(review.is_active)

    def test_mark_helpful(self):
        self.client.force_authenticate(user=self.other_user)
        # Create review using factory
        review = ProductReviewFactory(
            product=self.product, reviewer=self.user, rating=5, title="Helpful", comment="Helpful"
        )

        url = reverse("marketplace:review-mark-helpful", args=[review.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["voted"])
        self.assertEqual(response.data["helpful_count"], 1)

        # Unvote
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["voted"])
        self.assertEqual(response.data["helpful_count"], 0)

    def test_mark_own_review_helpful_fail(self):
        self.client.force_authenticate(user=self.user)
        # Create review using factory
        review = ProductReviewFactory(product=self.product, reviewer=self.user, rating=5)

        url = reverse("marketplace:review-mark-helpful", args=[review.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_reviews(self):
        ProductReviewFactory(product=self.product, reviewer=self.user, rating=5)
        ProductReviewFactory(product=self.product, reviewer=self.other_user, rating=4)

        response = self.client.get(self.review_list_url, {"product_id": str(self.product.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
