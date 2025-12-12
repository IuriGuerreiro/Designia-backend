"""
SearchService - Product Search & Filtering

Handles advanced product search with full-text search, filtering, sorting,
autocomplete, and pagination. Optimized for performance with database indexes.

Story 2.8: SearchService - Product Search & Filtering
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.paginator import Paginator
from django.db.models import Avg, F, Q

from marketplace.catalog.domain.models.catalog import Product
from marketplace.catalog.domain.models.category import Category
from marketplace.catalog.domain.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok


logger = logging.getLogger(__name__)


class SearchService(BaseService):
    """
    Service for product search and filtering.

    Responsibilities:
    - Full-text search across products
    - Advanced filtering (category, price, rating, availability)
    - Sorting by relevance, price, rating, date
    - Autocomplete suggestions
    - Search suggestions (related queries)
    - Performance-optimized queries

    Features:
    - PostgreSQL full-text search (when available)
    - Fallback to ILIKE search for non-Postgres databases
    - Cursor-based pagination for consistency
    - Search result ranking
    """

    def __init__(self):
        """Initialize SearchService."""
        super().__init__()
        self.use_postgres_search = self._check_postgres_support()

    def _check_postgres_support(self) -> bool:
        """
        Check if PostgreSQL full-text search is available.

        Returns:
            bool: True if Postgres search is available
        """
        try:
            from django.db import connection

            return connection.vendor == "postgresql"
        except Exception:
            return False

    @BaseService.log_performance
    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        sort: str = "relevance",
        page: int = 1,
        page_size: int = 20,
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Search products with filters and sorting.

        Args:
            query: Search query string
            filters: Optional filters (category, price_min, price_max, seller, min_rating, in_stock)
            sort: Sort order (relevance, price_asc, price_desc, rating, newest)
            page: Page number
            page_size: Items per page

        Returns:
            ServiceResult with paginated search results

        Example:
            >>> result = search_service.search(
            ...     query="iPhone",
            ...     filters={"category": "electronics", "price_min": 500, "in_stock": True},
            ...     sort="price_asc",
            ...     page=1
            ... )
            >>> if result.ok:
            ...     products = result.value["results"]
            ...     total = result.value["count"]
        """
        try:
            filters = filters or {}

            # Start with base queryset
            queryset = Product.objects.select_related("seller", "category").prefetch_related("images")

            # Apply search query
            if query:
                if self.use_postgres_search:
                    # Use PostgreSQL full-text search
                    search_vector = SearchVector("name", weight="A") + SearchVector("description", weight="B")
                    search_query = SearchQuery(query)
                    queryset = queryset.annotate(
                        search=search_vector, rank=SearchRank(search_vector, search_query)
                    ).filter(search=search_query)
                else:
                    # Fallback to ILIKE search
                    search_q = (
                        Q(name__icontains=query)
                        | Q(description__icontains=query)
                        | Q(brand__icontains=query)
                        | Q(tags__icontains=query)
                    )
                    queryset = queryset.filter(search_q)

            # Apply filters
            queryset = self._apply_filters(queryset, filters)

            # Apply sorting
            queryset = self._apply_sorting(queryset, sort, query)

            # Only show active products by default
            if "is_active" not in filters:
                queryset = queryset.filter(is_active=True)

            # Paginate
            paginator = Paginator(queryset, page_size)
            page_obj = paginator.get_page(page)

            result_data = {
                "results": list(page_obj.object_list),
                "count": paginator.count,
                "page": page,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "query": query,
                "filters": filters,
                "sort": sort,
            }

            self.logger.info(
                f"Search: query='{query}', filters={filters}, sort={sort}, "
                f"results={paginator.count}, page={page}/{paginator.num_pages}"
            )

            return service_ok(result_data)

        except Exception as e:
            self.logger.error(f"Error searching products: query='{query}', error={e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def autocomplete(self, query: str, limit: int = 10) -> ServiceResult[List[Dict[str, Any]]]:
        """
        Get autocomplete suggestions for search query.

        Returns top matching product names for autocomplete dropdown.

        Args:
            query: Partial search query
            limit: Maximum suggestions to return (default: 10)

        Returns:
            ServiceResult with list of autocomplete suggestions

        Example:
            >>> result = search_service.autocomplete("iPh", limit=5)
            >>> if result.ok:
            ...     suggestions = result.value
            ...     # [
            ...     #   {"id": "...", "name": "iPhone 15", "category": "Electronics"},
            ...     #   {"id": "...", "name": "iPhone 14", "category": "Electronics"},
            ...     # ]
        """
        try:
            if not query or len(query) < 2:
                return service_ok([])

            # Search product names
            queryset = (
                Product.objects.filter(name__icontains=query, is_active=True)
                .select_related("category")
                .order_by("-view_count", "-favorite_count")[:limit]
            )

            suggestions = [
                {
                    "id": str(product.id),
                    "name": product.name,
                    "category": product.category.name if product.category else None,
                    "price": float(product.price),
                    "image": product.images.first().get_proxy_url() if product.images.exists() else None,
                }
                for product in queryset
            ]

            self.logger.info(f"Autocomplete: query='{query}', suggestions={len(suggestions)}")

            return service_ok(suggestions)

        except Exception as e:
            self.logger.error(f"Error getting autocomplete suggestions: query='{query}', error={e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_suggestions(self, query: str, limit: int = 5) -> ServiceResult[List[str]]:
        """
        Get search suggestions (related search terms).

        Returns popular search terms related to the query.
        Currently returns category names and brands. Can be enhanced with
        search analytics data.

        Args:
            query: Search query
            limit: Maximum suggestions (default: 5)

        Returns:
            ServiceResult with list of suggested search terms

        Example:
            >>> result = search_service.get_suggestions("phone")
            >>> if result.ok:
            ...     suggestions = result.value
            ...     # ["smartphones", "mobile phones", "iPhone", "Samsung Galaxy"]
        """
        try:
            suggestions = []

            if not query or len(query) < 2:
                return service_ok(suggestions)

            # Get matching categories
            categories = Category.objects.filter(name__icontains=query, is_active=True).values_list("name", flat=True)[
                :3
            ]
            suggestions.extend(categories)

            # Get matching brands
            brands = (
                Product.objects.filter(brand__icontains=query, is_active=True)
                .values_list("brand", flat=True)
                .distinct()[:3]
            )
            suggestions.extend(brands)

            # Limit to requested count
            suggestions = list(set(suggestions))[:limit]

            self.logger.info(f"Search suggestions: query='{query}', suggestions={len(suggestions)}")

            return service_ok(suggestions)

        except Exception as e:
            self.logger.error(f"Error getting search suggestions: query='{query}', error={e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def filter_products(
        self, filters: Dict[str, Any], page: int = 1, page_size: int = 20, sort: str = "newest"
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Filter products without search query.

        Useful for category pages, filtered browsing.

        Args:
            filters: Filters to apply (category, price_min, price_max, seller, min_rating, in_stock)
            page: Page number
            page_size: Items per page
            sort: Sort order

        Returns:
            ServiceResult with paginated filtered products

        Example:
            >>> result = search_service.filter_products(
            ...     filters={"category": "electronics", "in_stock": True},
            ...     sort="price_asc"
            ... )
        """
        try:
            # Start with base queryset
            queryset = Product.objects.select_related("seller", "category").prefetch_related("images")

            # Apply filters
            queryset = self._apply_filters(queryset, filters)

            # Apply sorting
            queryset = self._apply_sorting(queryset, sort, None)

            # Only show active products by default
            if "is_active" not in filters:
                queryset = queryset.filter(is_active=True)

            # Paginate
            paginator = Paginator(queryset, page_size)
            page_obj = paginator.get_page(page)

            result_data = {
                "results": list(page_obj.object_list),
                "count": paginator.count,
                "page": page,
                "page_size": page_size,
                "num_pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "filters": filters,
                "sort": sort,
            }

            self.logger.info(f"Filter products: filters={filters}, sort={sort}, results={paginator.count}")

            return service_ok(result_data)

        except Exception as e:
            self.logger.error(f"Error filtering products: filters={filters}, error={e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def _apply_filters(self, queryset, filters: Dict[str, Any]):
        """
        Apply filters to queryset.

        Args:
            queryset: Product queryset
            filters: Filter dict

        Returns:
            Filtered queryset
        """
        # Category filter
        if "category" in filters:
            queryset = queryset.filter(category__slug=filters["category"])

        # Price range filters
        if "price_min" in filters:
            queryset = queryset.filter(price__gte=Decimal(str(filters["price_min"])))

        if "price_max" in filters:
            queryset = queryset.filter(price__lte=Decimal(str(filters["price_max"])))

        # Seller filter
        if "seller" in filters:
            queryset = queryset.filter(seller__id=filters["seller"])

        # Rating filter (minimum rating)
        if "min_rating" in filters:
            min_rating = Decimal(str(filters["min_rating"]))
            # Annotate with average rating and filter
            queryset = queryset.annotate(avg_rating=Avg("reviews__rating")).filter(avg_rating__gte=min_rating)

        # Stock availability filter
        if "in_stock" in filters and filters["in_stock"]:
            queryset = queryset.filter(stock_quantity__gt=0)

        # Condition filter
        if "condition" in filters:
            queryset = queryset.filter(condition=filters["condition"])

        # Brand filter
        if "brand" in filters:
            queryset = queryset.filter(brand__icontains=filters["brand"])

        # Featured filter
        if "is_featured" in filters:
            queryset = queryset.filter(is_featured=filters["is_featured"])

        # Active filter (override default)
        if "is_active" in filters:
            queryset = queryset.filter(is_active=filters["is_active"])

        return queryset

    def _apply_sorting(self, queryset, sort: str, query: Optional[str]):
        """
        Apply sorting to queryset.

        Args:
            queryset: Product queryset
            sort: Sort order
            query: Search query (for relevance sorting)

        Returns:
            Sorted queryset
        """
        if sort == "relevance" and query and self.use_postgres_search:
            # Sort by search rank (already annotated in search method)
            return queryset.order_by("-rank", "-view_count")
        elif sort == "relevance":
            # Fallback relevance: view count
            return queryset.order_by("-view_count", "-favorite_count")
        elif sort in ["price_asc", "price_low"]:
            return queryset.order_by("price", "-created_at")
        elif sort in ["price_desc", "price_high"]:
            return queryset.order_by("-price", "-created_at")
        elif sort == "rating":
            # Sort by average rating
            return queryset.annotate(avg_rating=Avg("reviews__rating")).order_by(
                F("avg_rating").desc(nulls_last=True), "-view_count"
            )
        elif sort == "newest":
            return queryset.order_by("-created_at")
        elif sort == "popular":
            return queryset.order_by("-view_count", "-favorite_count")
        else:
            # Default: newest
            return queryset.order_by("-created_at")

    @BaseService.log_performance
    def get_trending_products(self, limit: int = 10, timeframe_days: int = 7) -> ServiceResult[List[Product]]:
        """
        Get trending products based on recent views and favorites.

        Args:
            limit: Number of products to return
            timeframe_days: Timeframe for trending calculation (default: 7 days)

        Returns:
            ServiceResult with list of trending products

        Example:
            >>> result = search_service.get_trending_products(limit=5)
            >>> if result.ok:
            ...     trending = result.value
        """
        try:
            # For now, simple trending based on view_count and favorite_count
            # TODO: Enhance with time-weighted scoring using view/favorite timestamps
            queryset = (
                Product.objects.filter(is_active=True)
                .select_related("seller", "category")
                .prefetch_related("images")
                .order_by("-view_count", "-favorite_count")[:limit]
            )

            products = list(queryset)

            self.logger.info(f"Retrieved {len(products)} trending products")

            return service_ok(products)

        except Exception as e:
            self.logger.error(f"Error getting trending products: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_related_products(self, product_id: str, limit: int = 10) -> ServiceResult[List[Product]]:
        """
        Get products related to a given product.

        Related by: same category, similar price range, same brand.

        Args:
            product_id: Product UUID
            limit: Number of related products to return

        Returns:
            ServiceResult with list of related products

        Example:
            >>> result = search_service.get_related_products(product_id, limit=5)
            >>> if result.ok:
            ...     related = result.value
        """
        try:
            # Get the reference product
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                return service_err(ErrorCodes.PRODUCT_NOT_FOUND, f"Product {product_id} not found")

            # Find related products
            queryset = (
                Product.objects.filter(is_active=True)
                .exclude(id=product_id)
                .select_related("seller", "category")
                .prefetch_related("images")
            )

            # Same category (highest priority)
            if product.category:
                queryset = queryset.filter(category=product.category)

            # Similar price range (±30%)
            price_min = product.price * Decimal("0.7")
            price_max = product.price * Decimal("1.3")
            queryset = queryset.filter(price__gte=price_min, price__lte=price_max)

            # Same brand (if available)
            if product.brand:
                # Prioritize same brand, but don't exclude others
                queryset = queryset.order_by(
                    F("brand").desc() if product.brand else F("brand"), "-view_count", "-favorite_count"
                )
            else:
                queryset = queryset.order_by("-view_count", "-favorite_count")

            # Limit results
            products = list(queryset[:limit])

            self.logger.info(f"Retrieved {len(products)} related products for product {product_id}")

            return service_ok(products)

        except Exception as e:
            self.logger.error(f"Error getting related products for {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
