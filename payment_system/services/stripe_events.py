import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def summarize_event(event: Dict[str, Any]) -> str:
    """Return a safe, concise summary of a Stripe event for logging.

    Never include raw payloads, tokens, or PII.
    """
    evt_type = event.get("type", "unknown")
    obj = (event.get("data", {}) or {}).get("object", {})
    obj_type = obj.get("object")
    obj_id = obj.get("id")
    return f"type={evt_type} object={obj_type} id={obj_id}"


def handle_event(event: Dict[str, Any]) -> None:
    """Placeholder dispatcher for webhook events.

    Call into specific handlers here as we migrate logic out of views.
    """
    logger.info("Stripe event received: %s", summarize_event(event))
