import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from infrastructure.container import container
from marketplace.infra.observability.metrics import internal_api_calls_total

logger = logging.getLogger(__name__)

# Security Note: In a real environment, these internal APIs should be protected
# by network policies (only accessible from other internal services) or shared secrets.
# For now, we use AllowAny but mount them under a path that should be blocked by the Gateway/Nginx.


@api_view(["GET"])
@permission_classes([AllowAny])
def internal_get_product(request, product_id):
    """
    Internal API to get product info for other services.
    Returns: JSON with price, stock, active status.
    """
    logger.info(f"Internal API: get_product {product_id}")

    # Use DI container if possible, or direct service instantiation
    # Using container is better for testing/mocking
    catalog_service = container.catalog_service()

    result = catalog_service.get_product(product_id)

    if not result.ok:
        internal_api_calls_total.labels(endpoint="internal_get_product", status="failure").inc()
        return Response(
            {"error": result.error, "message": result.error_detail},
            status=status.HTTP_404_NOT_FOUND if result.error == "product_not_found" else status.HTTP_400_BAD_REQUEST,
        )

    product = result.value

    internal_api_calls_total.labels(endpoint="internal_get_product", status="success").inc()
    # Return minimal data needed by other services
    return Response(
        {
            "id": str(product.id),
            "name": product.name,
            "price": str(product.price),
            "stock_quantity": product.stock_quantity,
            "is_active": product.is_active,
            "seller_id": product.seller.id,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def internal_get_order(request, order_id):
    """
    Internal API to get order info for other services (e.g. Payment).
    """
    logger.info(f"Internal API: get_order {order_id}")
    # Internal view bypasses the "user is owner" check logic of standard service methods
    # But OrderService.get_order requires a user.
    # We might need a direct DB fetch here or a service method for system-level access.
    # For now, let's use the DB directly for this internal "system" view to avoid hacking the service permission logic,
    # OR better, add a `get_order_by_id` system method to the service.
    # Let's try to use the model directly here as a Facade for internal access
    # if the service enforces strict user context.

    from marketplace.ordering.domain.models.order import Order

    try:
        order = Order.objects.get(id=order_id)
        internal_api_calls_total.labels(endpoint="internal_get_order", status="success").inc()
        return Response(
            {
                "id": str(order.id),
                "status": order.status,
                "total_amount": str(order.total_amount),
                "buyer_id": order.buyer.id,
                "payment_status": order.payment_status,
                "created_at": order.created_at,
            }
        )
    except Order.DoesNotExist:
        internal_api_calls_total.labels(endpoint="internal_get_order", status="failure").inc()
        return Response(
            {"error": "order_not_found", "message": f"Order {order_id} not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        internal_api_calls_total.labels(endpoint="internal_get_order", status="error").inc()
        logger.error(f"Internal API Error: {e}")
        return Response({"error": "internal_error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
