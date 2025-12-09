from dataclasses import dataclass, field
from typing import Any, Dict

from django.utils import timezone


@dataclass
class DomainEvent:
    """Base class for all domain events in authentication context."""

    event_type: str
    occurred_at: str = field(default_factory=lambda: timezone.now().isoformat())
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize event to dictionary for publishing."""
        return {"event_type": self.event_type, "occurred_at": self.occurred_at, "payload": self.payload}

    @classmethod
    def from_dict(cls, data: dict) -> "DomainEvent":
        """Deserialize event from dictionary."""
        return cls(event_type=data["event_type"], occurred_at=data["occurred_at"], payload=data["payload"])
