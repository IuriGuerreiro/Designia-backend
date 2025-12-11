from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

from django.utils import timezone


@dataclass
class DomainEvent:
    """Base class for all domain events."""

    event_type: str
    occurred_at: datetime = field(default_factory=timezone.now)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"event_type": self.event_type, "occurred_at": self.occurred_at.isoformat(), "payload": self.payload}
