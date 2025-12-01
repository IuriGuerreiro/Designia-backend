from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from marketplace.models import Category, Order, OrderItem, Product, ProductReview

User = get_user_model()


class ReviewViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create users
        self.user = User.objects.create_user(username="user", password="password", email="user@example.com")
        self.seller = User.objects.create_user(
            username="seller", password="password", email="seller@example.com", role="seller"
        )
        self.other_user = User.objects.create_user(username="other", password="password", email="other@example.com")

        # Create category
        self.category = Category.objects.create(name="Electronics", slug="electronics")

        # Create product
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            description="Desc",
            price=100.00,
            seller=self.seller,
            category=self.category,
            stock_quantity=10,
            is_active=True,
        )

        # Create verified order for user
        self.order = Order.objects.create(
            buyer=self.user,
            status="delivered",
            subtotal=100.00,
            total_amount=100.00,
            shipping_address={"street": "123 Main St", "city": "Test City", "country": "Test Country"},
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=100.00,
            total_price=100.00,
            seller=self.seller,
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
        ProductReview.objects.create(
            product=self.product, reviewer=self.user, rating=5, title="First", comment="First"
        )

        data = {"product_id": str(self.product.id), "rating": 4, "title": "Second", "comment": "Second"}
        response = self.client.post(self.review_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already reviewed", response.data["detail"])

    def test_update_review_success(self):
        self.client.force_authenticate(user=self.user)
        review = ProductReview.objects.create(
            product=self.product, reviewer=self.user, rating=5, title="Old", comment="Old"
        )

        url = reverse("marketplace:review-detail", args=[review.id])
        data = {"rating": 4, "title": "New"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        review.refresh_from_db()
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.title, "New")

    def test_update_others_review_fail(self):
        self.client.force_authenticate(user=self.other_user)
        review = ProductReview.objects.create(
            product=self.product, reviewer=self.user, rating=5, title="User's", comment="User's"
        )

        url = reverse("marketplace:review-detail", args=[review.id])
        data = {"rating": 1}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_review_success(self):
        self.client.force_authenticate(user=self.user)
        review = ProductReview.objects.create(
            product=self.product, reviewer=self.user, rating=5, title="Del", comment="Del"
        )

        url = reverse("marketplace:review-detail", args=[review.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        review.refresh_from_db()
        self.assertFalse(review.is_active)

    def test_mark_helpful(self):
        self.client.force_authenticate(user=self.other_user)
        review = ProductReview.objects.create(
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
        review = ProductReview.objects.create(product=self.product, reviewer=self.user, rating=5)

        url = reverse("marketplace:review-mark-helpful", args=[review.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_reviews(self):
        ProductReview.objects.create(product=self.product, reviewer=self.user, rating=5)
        ProductReview.objects.create(product=self.product, reviewer=self.other_user, rating=4)

        response = self.client.get(self.review_list_url, {"product_id": str(self.product.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
