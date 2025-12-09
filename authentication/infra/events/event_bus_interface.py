from abc import ABC, abstractmethod
from typing import Callable


class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    def publish(self, event_type: str, payload: dict):
        """Publish event to bus."""
        pass

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to event type with handler function."""
        pass
