import logging

from django.db import models
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from activity.models import UserClick
from marketplace.filters import ProductFilter
from marketplace.models import Category, Product
from marketplace.serializers import CategorySerializer, ProductListSerializer

logger = logging.getLogger(__name__)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for categories - read-only operations
    """

    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = "slug"
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "description"]

    @action(detail=True, methods=["get"])
    def products(self, request, slug=None):
        """Get products in this category with view tracking"""
        category = self.get_object()
        products = (
            Product.objects.filter(category=category, is_active=True)
            .select_related("seller", "category")
            .prefetch_related("images", "reviews__reviewer", "favorited_by")
            .annotate(
                calculated_review_count=models.Count("reviews", filter=models.Q(reviews__is_active=True)),
                calculated_avg_rating=models.Avg("reviews__rating", filter=models.Q(reviews__is_active=True)),
            )
        )

        # Apply filtering
        filter_backend = ProductFilter()
        products = filter_backend.filter_queryset(request, products, self)

        # Track category views
        try:
            from marketplace.tracking_utils import MetricsHelper, SessionHelper

            user, session_key = SessionHelper.get_user_or_session(request)
            products_list = list(products)

            if products_list:
                MetricsHelper.bulk_ensure_metrics(products_list)

                for product in products_list:
                    try:
                        UserClick.track_activity(
                            product=product,
                            action="category_view",
                            user=user,
                            session_key=session_key,
                            request=request,
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error tracking category listing views: {str(e)}")

        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)
