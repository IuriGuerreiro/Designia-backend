from dataclasses import dataclass
from decimal import Decimal

from .base import DomainEvent


@dataclass
class OrderPlacedEvent(DomainEvent):
    """Event: Order placed."""

    def __init__(self, order_id: str, user_id: str, total_amount: Decimal):
        super().__init__(
            event_type="order.placed",
            payload={"order_id": order_id, "user_id": user_id, "total_amount": str(total_amount)},
        )


@dataclass
class OrderCancelledEvent(DomainEvent):
    """Event: Order cancelled."""

    def __init__(self, order_id: str, user_id: str, reason: str, payment_status: str):
        super().__init__(
            event_type="order.cancelled",
            payload={
                "order_id": order_id,
                "user_id": user_id,
                "reason": reason,
                "payment_status": payment_status,
            },
        )
