import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from marketplace.models import Category, Product, ProductReview
from marketplace.serializers import ProductDetailSerializer, ProductListSerializer
from marketplace.services.review_metrics_service import ReviewMetricsService

User = get_user_model()


class ReviewMetricsLogicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test_reviewer", email="reviewer@example.com", password="password", id=uuid.uuid4()
        )
        self.category = Category.objects.create(name="Review Test Cat", slug="review-test")
        self.product = Product.objects.create(
            name="Review Product",
            description="Desc",
            price=Decimal("10.00"),
            seller=self.user,
            category=self.category,
            is_active=True,
        )
        self.service = ReviewMetricsService()
        cache.clear()

    def test_metrics_service_calculations(self):
        """Test service logic directly"""
        # No reviews initially
        self.assertEqual(self.service.get_review_count(str(self.product.id)).value, 0)
        self.assertEqual(self.service.calculate_average_rating(str(self.product.id)).value, Decimal("0"))

        # Add reviews
        ProductReview.objects.create(product=self.product, reviewer=self.user, rating=5)
        self.service.invalidate_cache(str(self.product.id))  # Must invalidate manually or wait for timeout/trigger

        self.assertEqual(self.service.get_review_count(str(self.product.id)).value, 1)
        self.assertEqual(self.service.calculate_average_rating(str(self.product.id)).value, Decimal("5.00"))

        # Add another review (different user would be ideal, but simple test works)
        user2 = User.objects.create_user(
            username="reviewer2", email="reviewer2@example.com", password="password", id=uuid.uuid4()
        )
        ProductReview.objects.create(product=self.product, reviewer=user2, rating=1)
        self.service.invalidate_cache(str(self.product.id))

        self.assertEqual(self.service.get_review_count(str(self.product.id)).value, 2)
        # (5+1)/2 = 3.0
        self.assertEqual(self.service.calculate_average_rating(str(self.product.id)).value, Decimal("3.00"))

    def test_serializers_use_service(self):
        """Test that serializers retrieve metrics via service"""
        ProductReview.objects.create(product=self.product, reviewer=self.user, rating=4)
        self.service.invalidate_cache(str(self.product.id))

        # List Serializer
        serializer = ProductListSerializer(self.product)
        data = serializer.data
        self.assertEqual(data["review_count"], 1)
        self.assertEqual(Decimal(str(data["average_rating"])), Decimal("4.00"))

        # Detail Serializer
        serializer = ProductDetailSerializer(self.product)
        data = serializer.data
        self.assertEqual(data["review_count"], 1)
        self.assertEqual(Decimal(str(data["average_rating"])), Decimal("4.00"))

    def test_caching_behavior(self):
        """Test that service uses cache"""
        ProductReview.objects.create(product=self.product, reviewer=self.user, rating=5)

        # First call caches it
        self.service.calculate_average_rating(str(self.product.id))

        # Modify DB directly (bypass service invalidation)
        ProductReview.objects.filter(product=self.product, reviewer=self.user).update(rating=1)

        # Second call should return OLD value from cache
        result = self.service.calculate_average_rating(str(self.product.id))
        self.assertEqual(result.value, Decimal("5.00"))  # Still 5.0, not 3.0

        # Invalidate
        self.service.invalidate_cache(str(self.product.id))

        # Should now get new value
        result = self.service.calculate_average_rating(str(self.product.id))
        self.assertEqual(result.value, Decimal("1.00"))  # Now 1.0
