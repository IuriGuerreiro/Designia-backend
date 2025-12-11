"""
OrderService - Order Lifecycle Management

Handles order creation, updates, cancellation, and state management.
Orchestrates cart, inventory, and pricing services for complete order workflow.

Story 2.4: OrderService - Order Lifecycle Management
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

# Phase 3: Observability
from authentication.infra.observability.tracing import tracer
from infrastructure.events import get_event_bus
from marketplace.cart.domain.services.cart_service import CartService
from marketplace.cart.domain.services.inventory_service import InventoryService
from marketplace.cart.domain.services.pricing_service import PricingService
from marketplace.catalog.domain.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from marketplace.infra.observability.metrics import order_value, orders_placed_total
from marketplace.ordering.domain.models.order import Order, OrderItem

User = get_user_model()
logger = logging.getLogger(__name__)


class OrderService(BaseService):
    """
    Service for managing order lifecycle.
    """

    def __init__(
        self,
        cart_service: CartService = None,
        inventory_service: InventoryService = None,
        pricing_service: PricingService = None,
        event_bus=None,
    ):
        """
        Initialize OrderService.

        Args:
            cart_service: Service for cart operations (injected)
            inventory_service: Service for stock management (injected)
            pricing_service: Service for price calculations (injected)
            event_bus: Event bus for publishing domain events (injected)
        """
        super().__init__()  # BaseService does not take these args
        self.cart_service = cart_service or CartService()
        self.inventory_service = inventory_service or InventoryService()
        self.pricing_service = pricing_service or PricingService()
        self.event_bus = event_bus or get_event_bus()

    @BaseService.log_performance
    @transaction.atomic
    def create_order(
        self, user: User, shipping_address: Dict, buyer_notes: str = "", shipping_cost: Decimal = None
    ) -> ServiceResult[Order]:
        """
        Create order from user's cart.
        """
        with tracer.start_as_current_span("order_create_transaction") as span:
            span.set_attribute("user.id", str(user.id))

            try:
                # Step 1: Get and validate cart
                with tracer.start_as_current_span("get_cart"):
                    cart_result = self.cart_service.get_cart(user)
                    if not cart_result.ok:
                        return service_err(cart_result.error, cart_result.error_detail)

                    cart_data = cart_result.value
                    cart_items = cart_data["items"]

                    if not cart_items:
                        return service_err(ErrorCodes.CART_EMPTY, "Cannot create order from empty cart")

                # Validate cart (stock availability, active products)
                with tracer.start_as_current_span("validate_cart"):
                    validation_result = self.cart_service.validate_cart(user)
                    if not validation_result.ok:
                        return validation_result

                    validation = validation_result.value
                    if not validation["valid"]:
                        return service_err(
                            ErrorCodes.VALIDATION_ERROR,
                            f"Cart validation failed: {len(validation['issues'])} issues found",
                        )

                # Step 2: Reserve inventory for all items
                with tracer.start_as_current_span("reserve_inventory"):
                    reservations = []
                    for item in cart_items:
                        product = item["product"]
                        quantity = item["quantity"]

                        reserve_result = self.inventory_service.reserve_stock(
                            product_id=str(product.id), quantity=quantity, user_id=user.id
                        )

                        if not reserve_result.ok:
                            # Rollback: release already reserved items
                            self._rollback_reservations(reservations)
                            return service_err(
                                ErrorCodes.RESERVATION_FAILED,
                                f"Failed to reserve stock for {product.name}: {reserve_result.error_detail}",
                            )

                        reservations.append(
                            {"product_id": str(product.id), "quantity": quantity, "data": reserve_result.value}
                        )

                # Step 3: Calculate totals
                with tracer.start_as_current_span("calculate_totals"):
                    cart_items_for_pricing = [
                        {"product": item["product"], "quantity": item["quantity"]} for item in cart_items
                    ]

                    # Calculate shipping if not provided
                    if shipping_cost is None:
                        shipping_result = self.pricing_service.calculate_shipping_cost()
                        if not shipping_result.ok:
                            self._rollback_reservations(reservations)
                            return shipping_result
                        shipping_cost = shipping_result.value

                    total_result = self.pricing_service.calculate_order_total(
                        order_items=cart_items_for_pricing, shipping_cost=shipping_cost
                    )

                    if not total_result.ok:
                        self._rollback_reservations(reservations)
                        return total_result

                    totals = total_result.value

                # Step 4: Create order
                with tracer.start_as_current_span("save_order"):
                    order = Order.objects.create(
                        buyer=user,
                        status="pending_payment",
                        payment_status="pending",
                        subtotal=totals["subtotal"],
                        shipping_cost=totals["shipping"],
                        tax_amount=totals["tax"],
                        discount_amount=totals.get("coupon_discount", Decimal("0")),
                        total_amount=totals["total"],
                        shipping_address=shipping_address,
                        buyer_notes=buyer_notes,
                    )

                    # Create order items (snapshot of cart at order time)
                    for item in cart_items:
                        product = item["product"]
                        quantity = item["quantity"]

                        # Use prefetched images to avoid DB hit
                        product_images = list(product.images.all())
                        primary_image = product_images[0] if product_images else None
                        image_url = primary_image.get_proxy_url() if primary_image else ""

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            seller=product.seller,
                            quantity=quantity,
                            unit_price=product.price,  # Snapshot price
                            total_price=quantity * product.price,  # Calculate total_price
                            product_name=product.name,  # Snapshot name
                            product_description=product.description[:500] if product.description else "",  # Truncate
                            product_image=image_url,
                        )

                # Step 5: Clear cart
                clear_result = self.cart_service.clear_cart(user)
                if not clear_result.ok:
                    self.logger.warning(
                        f"Failed to clear cart after order creation for user {user.id}: {clear_result.error}"
                    )
                    # Don't rollback order - cart clear is not critical

                # Publish OrderPlacedEvent
                with tracer.start_as_current_span("publish_event"):
                    from marketplace.domain.events.order_events import OrderPlacedEvent

                    try:
                        event = OrderPlacedEvent(
                            order_id=str(order.id), user_id=str(user.id), total_amount=order.total_amount
                        )

                        # Publish to Redis event bus
                        self.event_bus.publish(event.event_type, event.payload)
                        self.logger.info(f"Published event: {event.to_dict()}")
                    except Exception as e:
                        self.logger.error(f"Failed to publish OrderPlacedEvent: {e}")
                        span.record_exception(e)

                # Metrics
                orders_placed_total.labels(status="success").inc()
                order_value.observe(float(order.total_amount))

                self.logger.info(
                    f"Created order {order.id} for user {user.id}: "
                    f"{len(cart_items)} items, total ${totals['total']}"
                )

                span.set_attribute("order.id", str(order.id))
                span.set_attribute("order.total", str(totals["total"]))

                return service_ok(order)

            except Exception as e:
                self.logger.error(f"Error creating order for user {user.id}: {e}", exc_info=True)
                span.record_exception(e)
                orders_placed_total.labels(status="failure").inc()  # Increment failure metric
                return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_order(self, order_id: str, user: User) -> ServiceResult[Order]:
        """
        Get order details (owner only).

        Args:
            order_id: Order UUID
            user: User requesting the order

        Returns:
            ServiceResult with Order instance

        Example:
            >>> result = order_service.get_order(order_id, user)
            >>> if result.ok:
            ...     order = result.value
        """
        try:
            order = Order.objects.select_related("buyer").prefetch_related("items__product").get(id=order_id)

            # Validate ownership
            if order.buyer != user:
                return service_err(ErrorCodes.NOT_ORDER_OWNER, "You do not own this order")

            self.logger.info(f"Retrieved order {order_id} for user {user.id}")

            return service_ok(order)

        except Order.DoesNotExist:
            return service_err(ErrorCodes.ORDER_NOT_FOUND, f"Order {order_id} not found")
        except Exception as e:
            self.logger.error(f"Error getting order {order_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def list_orders(
        self, user: User, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> ServiceResult[Dict]:
        """
        List user's orders with optional filtering.

        Args:
            user: User whose orders to list
            status: Optional status filter
            page: Page number
            page_size: Items per page

        Returns:
            ServiceResult with paginated order list

        Example:
            >>> result = order_service.list_orders(user, status="pending_payment")
            >>> if result.ok:
            ...     orders = result.value["results"]
        """
        try:
            queryset = Order.objects.filter(buyer=user).select_related("buyer").prefetch_related("items__product")

            # Apply filters
            if status:
                queryset = queryset.filter(status=status)

            # Order by newest first
            queryset = queryset.order_by("-created_at")

            # Simple pagination (could use Django Paginator for better pagination)
            offset = (page - 1) * page_size
            total_count = queryset.count()
            orders = list(queryset[offset : offset + page_size])

            result_data = {
                "results": orders,
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "num_pages": (total_count + page_size - 1) // page_size,
            }

            self.logger.info(f"Listed orders for user {user.id}: {total_count} total, page {page}")

            return service_ok(result_data)

        except Exception as e:
            self.logger.error(f"Error listing orders for user {user.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def list_seller_orders(
        self, seller: User, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> ServiceResult[Dict]:
        """
        List orders where the user is a seller.

        Args:
            seller: User who sold items
            status: Optional status filter
            page: Page number
            page_size: Items per page

        Returns:
            ServiceResult with paginated order list
        """
        try:
            # Filter orders containing items sold by this seller
            queryset = (
                Order.objects.filter(items__seller=seller)
                .distinct()
                .select_related("buyer")
                .prefetch_related("items__product")
            )

            # Apply filters
            if status:
                queryset = queryset.filter(status=status)

            # Order by newest first
            queryset = queryset.order_by("-created_at")

            # Simple pagination
            offset = (page - 1) * page_size
            total_count = queryset.count()
            orders = list(queryset[offset : offset + page_size])

            result_data = {
                "results": orders,
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "num_pages": (total_count + page_size - 1) // page_size,
            }

            self.logger.info(f"Listed seller orders for user {seller.id}: {total_count} total")

            return service_ok(result_data)

        except Exception as e:
            self.logger.error(f"Error listing seller orders for user {seller.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def update_shipping(
        self, order_id: str, user: User, tracking_number: str, carrier: str, carrier_code: str = ""
    ) -> ServiceResult[Order]:
        """
        Update order shipping information (admin/seller only).

        Also transitions order to 'shipped' status.

        Args:
            order_id: Order UUID
            user: User performing the update
            tracking_number: Tracking number
            carrier: Shipping carrier name
            carrier_code: Optional carrier code

        Returns:
            ServiceResult with updated Order
        """
        try:
            order = Order.objects.select_for_update().get(id=order_id)
            self.logger.debug(f"Update shipping for order {order_id}: order status={order.status}")

            # Validate order can be shipped
            if order.status not in ["payment_confirmed", "awaiting_shipment"]:
                self.logger.warning(
                    f"Update shipping: Invalid state transition for order {order_id} from {order.status}"
                )
                return service_err(
                    ErrorCodes.INVALID_ORDER_STATE,
                    f"Cannot ship order in status '{order.status}'. Must be payment_confirmed or awaiting_shipment.",
                )

            # Permission check: Only seller of items or staff can update shipping
            user_is_seller = order.items.filter(seller=user).exists()
            self.logger.debug(f"Update shipping: user {user.id} is_seller={user_is_seller}, is_staff={user.is_staff}")
            if not (user_is_seller or user.is_staff):
                self.logger.warning(f"Update shipping: Permission denied for user {user.id} on order {order_id}")
                return service_err(
                    ErrorCodes.PERMISSION_DENIED, "You don't have permission to update shipping for this order"
                )

            # Update shipping info
            order.tracking_number = tracking_number
            order.shipping_carrier = carrier
            order.carrier_code = carrier_code
            order.status = "shipped"
            order.shipped_at = timezone.now()

            order.save(update_fields=["tracking_number", "shipping_carrier", "carrier_code", "status", "shipped_at"])

            self.logger.info(f"Updated shipping for order {order_id}: {carrier} {tracking_number}")

            return service_ok(order)

        except Order.DoesNotExist:
            return service_err(ErrorCodes.ORDER_NOT_FOUND, f"Order {order_id} not found")
        except Exception as e:
            self.logger.error(f"Error updating shipping for order {order_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def cancel_order(self, order_id: str, user: User, reason: str = "") -> ServiceResult[Order]:
        """
        Cancel an order (owner only, before shipment).

        Releases reserved inventory back to stock.

        Args:
            order_id: Order UUID
            user: User cancelling the order
            reason: Cancellation reason

        Returns:
            ServiceResult with cancelled Order

        Example:
            >>> result = order_service.cancel_order(
            ...     order_id,
            ...     user=buyer_user,
            ...     reason="Changed my mind"
            ... )
        """
        try:
            order = (
                Order.objects.select_for_update()
                .select_related("buyer")
                .prefetch_related("items__product")
                .get(id=order_id)
            )

            # Validate ownership
            if order.buyer != user:
                return service_err(ErrorCodes.NOT_ORDER_OWNER, "You do not own this order")

            # Validate order can be cancelled
            if order.status in ["shipped", "delivered", "cancelled", "refunded"]:
                return service_err(ErrorCodes.ORDER_CANNOT_CANCEL, f"Cannot cancel order in status '{order.status}'")

            # Release inventory for all items
            for item in order.items.all():
                release_result = self.inventory_service.release_stock(
                    product_id=str(item.product.id), quantity=item.quantity, reason=f"order_cancelled_{order_id}"
                )

                if not release_result.ok:
                    self.logger.error(
                        f"Failed to release stock for product {item.product.id} "
                        f"when cancelling order {order_id}: {release_result.error}"
                    )
                    # Continue with cancellation even if stock release fails

            # Update order status
            order.status = "cancelled"
            order.cancellation_reason = reason
            order.cancelled_by = user
            order.cancelled_at = timezone.now()

            order.save(update_fields=["status", "cancellation_reason", "cancelled_by", "cancelled_at"])

            self.logger.info(f"Cancelled order {order_id} by user {user.id}: {reason}")

            return service_ok(order)

        except Order.DoesNotExist:
            return service_err(ErrorCodes.ORDER_NOT_FOUND, f"Order {order_id} not found")
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def _rollback_reservations(self, reservations: List[Dict]) -> None:
        """
        Release all reserved inventory (rollback helper).

        Args:
            reservations: List of reservation dicts with product_id and quantity
        """
        self.logger.warning(f"Rolling back {len(reservations)} inventory reservations")

        for reservation in reservations:
            product_id = reservation["product_id"]
            quantity = reservation["quantity"]

            release_result = self.inventory_service.release_stock(
                product_id=product_id, quantity=quantity, reason="order_creation_rollback"
            )

            if not release_result.ok:
                self.logger.error(
                    f"Failed to release stock during rollback: "
                    f"product={product_id}, quantity={quantity}, error={release_result.error}"
                )

    @BaseService.log_performance
    @transaction.atomic
    def confirm_payment(self, order_id: str) -> ServiceResult[Order]:
        """
        Confirm payment for an order (called by payment webhook).

        Transitions order from pending_payment → payment_confirmed.

        Args:
            order_id: Order UUID

        Returns:
            ServiceResult with updated Order

        Example:
            >>> result = order_service.confirm_payment(order_id)
        """
        try:
            order = Order.objects.select_for_update().get(id=order_id)

            # Validate order state
            if order.payment_status == "paid":
                self.logger.info(f"Order {order_id} payment already confirmed, skipping")
                return service_ok(order)

            if order.status != "pending_payment":
                return service_err(
                    ErrorCodes.INVALID_ORDER_STATE,
                    f"Cannot confirm payment for order in status '{order.status}'",
                )

            # Update payment and order status
            order.payment_status = "paid"
            order.status = "payment_confirmed"
            order.processed_at = timezone.now()

            order.save(update_fields=["payment_status", "status", "processed_at"])

            self.logger.info(f"Confirmed payment for order {order_id}")

            return service_ok(order)

        except Order.DoesNotExist:
            return service_err(ErrorCodes.ORDER_NOT_FOUND, f"Order {order_id} not found")
        except Exception as e:
            self.logger.error(f"Error confirming payment for order {order_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
