import logging

from authentication.infra.events.redis_event_bus import get_event_bus

logger = logging.getLogger(__name__)


def register_authentication_listeners():
    """
    Register all event listeners for authentication context.
    Called when Django app starts.
    """
    event_bus = get_event_bus()

    # Internal listeners (within authentication context)
    event_bus.subscribe("user.registered", log_user_registration)
    event_bus.subscribe("seller.approved", log_seller_approval)
    event_bus.subscribe("seller.rejected", log_seller_rejection)

    logger.info("Authentication event listeners registered")


def log_user_registration(event):
    """Log user registration event."""
    # event is the full envelope including 'payload'
    payload = event.get("payload", {})
    user_id = payload.get("user_id")
    email = payload.get("email")
    logger.info(f"[LISTENER] User registered: {email} ({user_id})")


def log_seller_approval(event):
    """Log seller approval event."""
    payload = event.get("payload", {})
    user_id = payload.get("user_id")
    seller_type = payload.get("seller_type")
    logger.info(f"[LISTENER] Seller approved: {user_id} as {seller_type}")


def log_seller_rejection(event):
    """Log seller rejection event."""
    payload = event.get("payload", {})
    user_id = payload.get("user_id")
    reason = payload.get("reason")
    logger.info(f"[LISTENER] Seller rejected: {user_id}. Reason: {reason}")
