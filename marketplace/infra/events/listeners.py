import logging

from infrastructure.events import get_event_bus


logger = logging.getLogger(__name__)


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


def register_marketplace_listeners():
    """Register all marketplace event listeners."""
    event_bus = get_event_bus()
    event_bus.subscribe("order.placed", handle_order_placed)
    logger.info("Marketplace event listeners registered")
