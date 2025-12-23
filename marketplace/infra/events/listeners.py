import logging
from decimal import Decimal

from infrastructure.events import get_event_bus
from marketplace.ordering.domain.services.order_service import OrderService


logger = logging.getLogger(__name__)

# ... (handle_order_placed and handle_payment_succeeded remain)


def handle_order_placed(event_data):
    """Handle order.placed event."""
    try:
        payload = event_data.get("payload", {})
        order_id = payload.get("order_id")
        logger.info(f"[Marketplace Listener] Order placed: {order_id}. Triggering async tasks...")
        # Placeholder for tasks like:
        # - Send email confirmation
        # - Update analytics
        # - Notify seller
    except Exception as e:
        logger.error(f"Error handling order.placed event: {e}")


def handle_payment_succeeded(event_data):
    """Handle payment.succeeded event."""
    try:
        payload = event_data.get("payload", {})
        order_id = payload.get("order_id")
        shipping_details = payload.get("shipping_details")

        logger.info(f"[Marketplace Listener] Payment succeeded for order {order_id}")

        service = OrderService()
        result = service.confirm_payment(order_id, shipping_details)

        if not result.ok:
            logger.error(f"Failed to confirm payment via listener for order {order_id}: {result.error_detail}")
        else:
            logger.info(f"Successfully confirmed payment for order {order_id}")

    except Exception as e:
        logger.error(f"Error handling payment.succeeded event: {e}")


def handle_payment_refunded(event_data):
    """Handle payment.refunded event."""
    try:
        payload = event_data.get("payload", {})
        order_id = payload.get("order_id")
        amount = Decimal(str(payload.get("amount", "0")))
        reason = payload.get("reason", "")

        logger.info(f"[Marketplace Listener] Payment refunded for order {order_id}")

        service = OrderService()
        result = service.process_refund_success(order_id, amount, reason)

        if not result.ok:
            logger.error(f"Failed to process refund success for order {order_id}: {result.error_detail}")

    except Exception as e:
        logger.error(f"Error handling payment.refunded event: {e}")


def handle_payment_refund_failed(event_data):
    """Handle payment.refund_failed event."""
    try:
        payload = event_data.get("payload", {})
        order_id = payload.get("order_id")
        reason = payload.get("reason", "")
        amount = Decimal(str(payload.get("amount", "0")))

        logger.info(f"[Marketplace Listener] Payment refund failed for order {order_id}")

        service = OrderService()
        result = service.process_refund_failure(order_id, reason, amount)

        if not result.ok:
            logger.error(f"Failed to process refund failure for order {order_id}: {result.error_detail}")

    except Exception as e:
        logger.error(f"Error handling payment.refund_failed event: {e}")


def handle_payment_failed(event_data):
    """Handle payment.failed event."""
    try:
        payload = event_data.get("payload", {})
        order_id = payload.get("order_id")
        reason = payload.get("reason", "Payment failed")

        logger.info(f"[Marketplace Listener] Payment failed for order {order_id}")

        service = OrderService()
        result = service.fail_payment(order_id, reason)

        if not result.ok:
            logger.error(f"Failed to process payment failure for order {order_id}: {result.error_detail}")

    except Exception as e:
        logger.error(f"Error handling payment.failed event: {e}")


def register_marketplace_listeners():
    """Register all marketplace event listeners."""
    event_bus = get_event_bus()
    event_bus.subscribe("order.placed", handle_order_placed)
    event_bus.subscribe("payment.succeeded", handle_payment_succeeded)
    event_bus.subscribe("payment.refunded", handle_payment_refunded)
    event_bus.subscribe("payment.refund_failed", handle_payment_refund_failed)
    event_bus.subscribe("payment.failed", handle_payment_failed)
    logger.info("Marketplace event listeners registered")
