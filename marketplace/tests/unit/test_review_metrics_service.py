from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from marketplace.catalog.domain.services.review_metrics_service import ReviewMetricsService


@pytest.mark.unit
class TestReviewMetricsServiceUnit:
    def setup_method(self):
        self.service = ReviewMetricsService()
        self.product_id = "test-product-id"

    @patch("marketplace.catalog.domain.services.review_metrics_service.cache")
    @patch("marketplace.models.ProductReview.objects.filter")
    def test_calculate_average_rating_cached(self, mock_filter, mock_cache):
        # Setup cache hit
        mock_cache.get.return_value = 4.5

        result = self.service.calculate_average_rating(self.product_id, use_cache=True)

        assert result.ok
        assert result.value == Decimal("4.5")
        mock_filter.assert_not_called()

    @patch("marketplace.catalog.domain.services.review_metrics_service.cache")
    @patch("marketplace.models.ProductReview.objects.filter")
    def test_calculate_average_rating_db(self, mock_filter, mock_cache):
        # Setup cache miss
        mock_cache.get.return_value = None

        # Mock DB aggregation
        mock_queryset = MagicMock()
        mock_queryset.exists.return_value = True
        mock_queryset.aggregate.return_value = {"rating__avg": 4.25}
        mock_filter.return_value = mock_queryset

        result = self.service.calculate_average_rating(self.product_id, use_cache=True)

        assert result.ok
        assert result.value == Decimal("4.25")
        mock_cache.set.assert_called()

    @patch("marketplace.catalog.domain.services.review_metrics_service.cache")
    @patch("marketplace.models.ProductReview.objects.filter")
    def test_get_review_count(self, mock_filter, mock_cache):
        mock_cache.get.return_value = None
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 10
        mock_filter.return_value = mock_queryset

        result = self.service.get_review_count(self.product_id)

        assert result.ok
        assert result.value == 10

    @patch("marketplace.catalog.domain.services.review_metrics_service.cache")
    @patch("marketplace.models.ProductReview.objects.filter")
    def test_get_rating_distribution(self, mock_filter, mock_cache):
        mock_cache.get.return_value = None

        # Mock annotation result: 2 five-star reviews, 1 one-star review
        mock_queryset = MagicMock()
        mock_queryset.values.return_value.annotate.return_value.order_by.return_value = [
            {"rating": 5, "count": 2},
            {"rating": 1, "count": 1},
        ]
        mock_filter.return_value = mock_queryset

        result = self.service.get_rating_distribution(self.product_id)

        assert result.ok
        distribution = result.value
        assert distribution[5] == 2
        assert distribution[1] == 1
        assert distribution[3] == 0  # Ensure defaults
