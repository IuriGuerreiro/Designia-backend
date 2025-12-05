"""
ReviewMetricsService - Review Aggregations

Handles product review metrics including average ratings, rating distributions,
and review counts. Supports caching for performance.

Story 2.7: ReviewMetricsService - Review Aggregations
"""

import logging
from decimal import Decimal
from typing import Dict, List

from django.core.cache import cache
from django.db.models import Avg, Count

from marketplace.models import Product, ProductReview

from .base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok

logger = logging.getLogger(__name__)


class ReviewMetricsService(BaseService):
    """
    Service for calculating and caching product review metrics.

    Responsibilities:
    - Calculate average ratings
    - Get rating distribution (star breakdown)
    - Get review counts
    - Update metrics (for cache refresh)
    - Get top reviews

    Supports caching for performance optimization.
    """

    def __init__(self, cache_timeout: int = 3600):
        """
        Initialize ReviewMetricsService.

        Args:
            cache_timeout: Cache timeout in seconds (default: 1 hour)
        """
        super().__init__()
        self.cache_timeout = cache_timeout

    @BaseService.log_performance
    def calculate_average_rating(self, product_id: str, use_cache: bool = True) -> ServiceResult[Decimal]:
        """
        Calculate average rating for a product.

        Args:
            product_id: Product UUID
            use_cache: Whether to use cached value (default: True)

        Returns:
            ServiceResult with average rating (0-5, or 0 if no reviews)

        Example:
            >>> result = review_metrics_service.calculate_average_rating(product_id)
            >>> if result.ok:
            ...     avg_rating = result.value
            ...     print(f"Average: {avg_rating:.1f} stars")
        """
        try:
            cache_key = f"product_avg_rating_{product_id}"

            # Try cache first
            if use_cache:
                cached_value = cache.get(cache_key)
                if cached_value is not None:
                    self.logger.debug(f"Cache hit for average rating: product={product_id}")
                    return service_ok(Decimal(str(cached_value)))

            # Calculate from database
            reviews = ProductReview.objects.filter(product_id=product_id, is_active=True)

            if not reviews.exists():
                avg_rating = Decimal("0")
            else:
                avg = reviews.aggregate(Avg("rating"))["rating__avg"]
                avg_rating = Decimal(str(round(avg, 2))) if avg else Decimal("0")

            # Cache the result
            cache.set(cache_key, float(avg_rating), self.cache_timeout)

            self.logger.info(f"Calculated average rating for product {product_id}: {avg_rating}")

            return service_ok(avg_rating)

        except Product.DoesNotExist:
            return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")
        except Exception as e:
            self.logger.error(f"Error calculating average rating for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_rating_distribution(self, product_id: str, use_cache: bool = True) -> ServiceResult[Dict[int, int]]:
        """
        Get rating distribution (count per star level).

        Args:
            product_id: Product UUID
            use_cache: Whether to use cached value (default: True)

        Returns:
            ServiceResult with dict mapping star level (1-5) to count

        Example:
            >>> result = review_metrics_service.get_rating_distribution(product_id)
            >>> if result.ok:
            ...     distribution = result.value
            ...     # {5: 120, 4: 45, 3: 10, 2: 3, 1: 2}
        """
        try:
            cache_key = f"product_rating_dist_{product_id}"

            # Try cache first
            if use_cache:
                cached_value = cache.get(cache_key)
                if cached_value is not None:
                    self.logger.debug(f"Cache hit for rating distribution: product={product_id}")
                    return service_ok(cached_value)

            # Calculate from database
            reviews = ProductReview.objects.filter(product_id=product_id, is_active=True)

            # Count reviews per rating
            distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

            rating_counts = reviews.values("rating").annotate(count=Count("id")).order_by("rating")

            for item in rating_counts:
                distribution[item["rating"]] = item["count"]

            # Cache the result
            cache.set(cache_key, distribution, self.cache_timeout)

            self.logger.info(f"Calculated rating distribution for product {product_id}: {distribution}")

            return service_ok(distribution)

        except Exception as e:
            self.logger.error(f"Error calculating rating distribution for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_review_count(self, product_id: str, use_cache: bool = True) -> ServiceResult[int]:
        """
        Get total review count for a product.

        Args:
            product_id: Product UUID
            use_cache: Whether to use cached value (default: True)

        Returns:
            ServiceResult with review count

        Example:
            >>> result = review_metrics_service.get_review_count(product_id)
            >>> if result.ok:
            ...     count = result.value
        """
        try:
            cache_key = f"product_review_count_{product_id}"

            # Try cache first
            if use_cache:
                cached_value = cache.get(cache_key)
                if cached_value is not None:
                    self.logger.debug(f"Cache hit for review count: product={product_id}")
                    return service_ok(cached_value)

            # Count from database
            count = ProductReview.objects.filter(product_id=product_id, is_active=True).count()

            # Cache the result
            cache.set(cache_key, count, self.cache_timeout)

            self.logger.info(f"Review count for product {product_id}: {count}")

            return service_ok(count)

        except Exception as e:
            self.logger.error(f"Error getting review count for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def update_metrics(self, product_id: str) -> ServiceResult[Dict]:
        """
        Update (refresh) all metrics for a product.

        Recalculates metrics by bypassing the cache and then updates the cache with fresh values.
        This method is typically called by a Celery task or Signal when a review is added, updated, or deleted.

        Args:
            product_id: Product UUID

        Returns:
            ServiceResult with all metrics:
            - average_rating
            - review_count
            - rating_distribution
            - updated_at
        """
        try:
            # Recalculate all metrics (bypass cache)
            avg_result = self.calculate_average_rating(product_id, use_cache=False)
            if not avg_result.ok:
                return avg_result

            count_result = self.get_review_count(product_id, use_cache=False)
            if not count_result.ok:
                return count_result

            dist_result = self.get_rating_distribution(product_id, use_cache=False)
            if not dist_result.ok:
                return dist_result

            metrics = {
                "average_rating": float(avg_result.value),
                "review_count": count_result.value,
                "rating_distribution": dist_result.value,
                "updated_at": None,  # TODO: Add timestamp
            }

            self.logger.info(f"Updated metrics for product {product_id}: {metrics}")

            return service_ok(metrics)

        except Exception as e:
            self.logger.error(f"Error updating metrics for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_top_reviews(self, product_id: str, limit: int = 10) -> ServiceResult[List[ProductReview]]:
        """
        Get top reviews for a product.

        Sorted by: verified purchase (prioritized), rating (high first), created date.

        Args:
            product_id: Product UUID
            limit: Maximum number of reviews to return (default: 10)

        Returns:
            ServiceResult with list of ProductReview instances

        Example:
            >>> result = review_metrics_service.get_top_reviews(product_id, limit=5)
            >>> if result.ok:
            ...     top_reviews = result.value
        """
        try:
            reviews = (
                ProductReview.objects.filter(product_id=product_id, is_active=True)
                .select_related("reviewer", "product")
                .order_by("-is_verified_purchase", "-rating", "-created_at")[:limit]
            )

            reviews_list = list(reviews)

            self.logger.info(f"Retrieved {len(reviews_list)} top reviews for product {product_id}")

            return service_ok(reviews_list)

        except Exception as e:
            self.logger.error(f"Error getting top reviews for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_all_metrics(self, product_id: str, use_cache: bool = True) -> ServiceResult[Dict]:
        """
        Get all metrics for a product in one call.

        More efficient than calling individual methods when all metrics are needed.

        Args:
            product_id: Product UUID
            use_cache: Whether to use cached values (default: True)

        Returns:
            ServiceResult with complete metrics dict

        Example:
            >>> result = review_metrics_service.get_all_metrics(product_id)
            >>> if result.ok:
            ...     metrics = result.value
            ...     print(f"Average: {metrics['average_rating']}")
            ...     print(f"Total: {metrics['review_count']}")
            ...     print(f"Distribution: {metrics['rating_distribution']}")
        """
        try:
            # Get all metrics
            avg_result = self.calculate_average_rating(product_id, use_cache)
            if not avg_result.ok:
                return avg_result

            count_result = self.get_review_count(product_id, use_cache)
            if not count_result.ok:
                return count_result

            dist_result = self.get_rating_distribution(product_id, use_cache)
            if not dist_result.ok:
                return dist_result

            metrics = {
                "product_id": str(product_id),
                "average_rating": float(avg_result.value),
                "review_count": count_result.value,
                "rating_distribution": dist_result.value,
            }

            return service_ok(metrics)

        except Exception as e:
            self.logger.error(f"Error getting all metrics for product {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def invalidate_cache(self, product_id: str) -> None:
        """
        Invalidate (clear) cached metrics for a product.

        Call this when a review is added/updated/deleted to force recalculation.

        Args:
            product_id: Product UUID

        Example:
            >>> review_metrics_service.invalidate_cache(product_id)
            >>> # Next get_all_metrics() will recalculate
        """
        cache_keys = [
            f"product_avg_rating_{product_id}",
            f"product_rating_dist_{product_id}",
            f"product_review_count_{product_id}",
        ]

        for key in cache_keys:
            cache.delete(key)

        self.logger.info(f"Invalidated cache for product {product_id}")
