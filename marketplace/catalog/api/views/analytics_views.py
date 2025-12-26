from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from marketplace.catalog.api.serializers.analytics_serializers import SellerAnalyticsSerializer
from marketplace.catalog.domain.models.catalog import Product
from marketplace.ordering.domain.models.order import Order, OrderItem
from marketplace.permissions import IsSellerUser


class SellerAnalyticsView(APIView):
    """
    API view for seller dashboard analytics.
    Returns aggregated metrics for the authenticated seller.
    """

    permission_classes = [IsAuthenticated, IsSellerUser]

    def get(self, request):
        seller = request.user

        # Parse period filter (optional)
        period = request.query_params.get("period", "all")
        period_start = None
        period_end = timezone.now()

        if period == "today":
            period_start = period_end.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            period_start = period_end - timedelta(days=7)
        elif period == "month":
            period_start = period_end - timedelta(days=30)
        elif period == "year":
            period_start = period_end - timedelta(days=365)
        # "all" means no period filter

        # Get seller's products
        products = Product.objects.filter(seller=seller)
        total_products = products.count()
        active_products = products.filter(is_active=True).count()

        # Aggregate product metrics
        product_metrics = products.aggregate(
            total_views=Sum("view_count"),
            total_clicks=Sum("click_count"),
            total_favorites=Sum("favorite_count"),
        )
        total_views = product_metrics["total_views"] or 0
        total_clicks = product_metrics["total_clicks"] or 0
        total_favorites = product_metrics["total_favorites"] or 0

        # Get seller's order items (filtered by period if specified)
        order_items_qs = OrderItem.objects.filter(seller=seller)
        if period_start:
            order_items_qs = order_items_qs.filter(order__created_at__gte=period_start)

        # Calculate revenue and items sold (only from paid orders)
        paid_statuses = ["payment_confirmed", "awaiting_shipment", "shipped", "delivered"]
        paid_order_items = order_items_qs.filter(order__status__in=paid_statuses)

        revenue_data = paid_order_items.aggregate(
            total_revenue=Sum("total_price"),
            total_items_sold=Sum("quantity"),
        )
        total_revenue = revenue_data["total_revenue"] or 0
        total_items_sold = revenue_data["total_items_sold"] or 0

        # Get unique orders for this seller
        seller_order_ids = order_items_qs.values_list("order_id", flat=True).distinct()
        orders_qs = Order.objects.filter(id__in=seller_order_ids)
        total_orders = orders_qs.count()

        # Orders by status
        status_counts = orders_qs.values("status").annotate(count=Count("id"))
        orders_by_status = {
            "pending_payment": 0,
            "payment_confirmed": 0,
            "awaiting_shipment": 0,
            "shipped": 0,
            "delivered": 0,
            "cancelled": 0,
            "refunded": 0,
            "return_requested": 0,
        }
        for item in status_counts:
            if item["status"] in orders_by_status:
                orders_by_status[item["status"]] = item["count"]

        # Pending fulfillment = awaiting_shipment orders
        pending_fulfillment_count = orders_by_status["awaiting_shipment"]

        # Calculate conversion rates
        view_to_click_rate = (total_clicks / total_views * 100) if total_views > 0 else 0.0
        click_to_sale_rate = (total_items_sold / total_clicks * 100) if total_clicks > 0 else 0.0

        # Top 5 products by revenue
        top_products_qs = (
            paid_order_items.values("product_id", "product__name", "product__slug")
            .annotate(
                total_sold=Sum("quantity"),
                revenue=Sum("total_price"),
            )
            .order_by("-revenue")[:5]
        )

        # Enrich with view counts
        top_products = []
        for item in top_products_qs:
            product = products.filter(id=item["product_id"]).first()
            top_products.append(
                {
                    "id": item["product_id"],
                    "name": item["product__name"],
                    "slug": item["product__slug"],
                    "total_sold": item["total_sold"],
                    "revenue": item["revenue"],
                    "views": product.view_count if product else 0,
                }
            )

        # Recent 5 orders
        recent_orders_qs = orders_qs.order_by("-created_at")[:5]
        recent_orders = []
        for order in recent_orders_qs:
            items_count = order.items.filter(seller=seller).count()
            recent_orders.append(
                {
                    "id": order.id,
                    "buyer_username": order.buyer.username,
                    "total_amount": order.total_amount,
                    "status": order.status,
                    "created_at": order.created_at,
                    "items_count": items_count,
                }
            )

        # Build response data
        analytics_data = {
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_products": total_products,
            "active_products": active_products,
            "total_items_sold": total_items_sold,
            "total_views": total_views,
            "total_clicks": total_clicks,
            "total_favorites": total_favorites,
            "view_to_click_rate": round(view_to_click_rate, 2),
            "click_to_sale_rate": round(click_to_sale_rate, 2),
            "orders_by_status": orders_by_status,
            "pending_fulfillment_count": pending_fulfillment_count,
            "top_products": top_products,
            "recent_orders": recent_orders,
            "period_start": period_start,
            "period_end": period_end if period_start else None,
        }

        serializer = SellerAnalyticsSerializer(analytics_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
