import logging

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from infrastructure.container import container
from marketplace.api.serializers import (
    ErrorResponseSerializer,
    InternalOrderInfoSerializer,
    InternalProductInfoSerializer,
)
from marketplace.infra.observability.metrics import internal_api_calls_total

logger = logging.getLogger(__name__)

# Security Note: In a real environment, these internal APIs should be protected
# by network policies (only accessible from other internal services) or shared secrets.
# For now, we use AllowAny but mount them under a path that should be blocked by the Gateway/Nginx.


@extend_schema(
    operation_id="internal_get_product",
    summary="[INTERNAL] Get product information",
    description="""
    **Internal API for service-to-service communication.**

    Returns minimal product data needed by other services (e.g., Payment, Notifications).

    **What it receives:**
    - `product_id` (UUID in URL): The product to fetch

    **What it returns:**
    - Product ID, name, price, stock quantity, active status, seller ID

    **Security:**
    - Should only be accessible within internal network
    - NOT exposed through Kong Gateway to public
    - Protected by network policies or firewall rules

    **Use Cases:**
    - Payment service checking product price before processing
    - Notification service getting product details for emails
    - Inventory service validating product exists
    """,
    responses={
        200: OpenApiResponse(
            response=InternalProductInfoSerializer,
            description="Product information retrieved successfully",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "name": "iPhone 15 Pro",
                        "price": "999.00",
                        "stock_quantity": 10,
                        "is_active": True,
                        "seller_id": 42,
                    },
                )
            ],
        ),
        404: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Product not found or inactive",
            examples=[
                OpenApiExample(
                    "Not Found",
                    value={"error": "product_not_found", "message": "Product not found or inactive"},
                )
            ],
        ),
        400: OpenApiResponse(response=ErrorResponseSerializer, description="Invalid product ID format"),
    },
    tags=["Marketplace - Internal"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def internal_get_product(request, product_id):
    """
    Internal API to get product info for other services.

    **Receives:** product_id (UUID)
    **Returns:** JSON with price, stock, active status, seller_id
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


@extend_schema(
    operation_id="internal_get_order",
    summary="[INTERNAL] Get order information",
    description="""
    **Internal API for service-to-service communication.**

    Returns order data needed by other services (e.g., Payment webhooks, Notification service).

    **What it receives:**
    - `order_id` (UUID in URL): The order to fetch

    **What it returns:**
    - Order ID, status, total amount, buyer ID, payment status, creation timestamp

    **Security:**
    - Should only be accessible within internal network
    - NOT exposed through Kong Gateway to public
    - Used by Payment service for webhook processing

    **Use Cases:**
    - Payment webhook confirming payment for an order
    - Notification service sending order status updates
    - Analytics service tracking order metrics
    """,
    responses={
        200: OpenApiResponse(
            response=InternalOrderInfoSerializer,
            description="Order information retrieved successfully",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "id": "789e4567-e89b-12d3-a456-426614174999",
                        "status": "pending_payment",
                        "total_amount": "1249.99",
                        "buyer_id": 123,
                        "payment_status": "pending",
                        "created_at": "2025-12-11T18:30:00Z",
                    },
                )
            ],
        ),
        404: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Order not found",
            examples=[OpenApiExample("Not Found", value={"error": "order_not_found", "message": "Order not found"})],
        ),
        500: OpenApiResponse(
            response=ErrorResponseSerializer,
            description="Internal error",
            examples=[
                OpenApiExample("Error", value={"error": "internal_error", "message": "Database connection failed"})
            ],
        ),
    },
    tags=["Marketplace - Internal"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def internal_get_order(request, order_id):
    """
    Internal API to get order info for other services (e.g. Payment webhooks).

    **Receives:** order_id (UUID)
    **Returns:** JSON with status, total_amount, buyer_id, payment_status
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
