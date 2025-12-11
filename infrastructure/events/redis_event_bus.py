import json
import logging
import threading
from typing import Callable

import redis
from django.conf import settings

from .event_bus_interface import EventBus


logger = logging.getLogger(__name__)


class RedisEventBus(EventBus):
    """Redis pub/sub implementation of event bus."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        # Handle cases where CELERY_BROKER_URL might be a list or complex object, though usually string
        if not isinstance(self.redis_url, str):
            # Fallback or simplified handling if needed, but assuming string for standard Celery config
            self.redis_url = "redis://localhost:6379/0"

        try:
            self.redis_client = redis.from_url(self.redis_url)
        except Exception as e:
            logger.error(f"Failed to connect to Redis at {self.redis_url}: {e}")
            self.redis_client = None

        self._subscribers = {}
        self._listening = False

    def publish(self, event_type: str, payload: dict):
        """Publish event to Redis channel."""
        if not self.redis_client:
            logger.warning(f"Redis client not available. Event {event_type} dropped.")
            return

        try:
            from django.utils import timezone

            message = {"event_type": event_type, "occurred_at": timezone.now().isoformat(), "payload": payload}
            channel = f"events.{event_type}"
            self.redis_client.publish(channel, json.dumps(message))
            logger.info(f"Published event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {str(e)}")
            # Don't raise - event publishing should not break business logic

    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to event channel."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.info(f"Registered handler for event: {event_type}")

    def start_listening(self):
        """Start listening to subscribed channels (background thread)."""
        if self._listening or not self.redis_client:
            return

        def listen():
            try:
                pubsub = self.redis_client.pubsub()
                channels = [f"events.{et}" for et in self._subscribers.keys()]

                if not channels:
                    return

                pubsub.subscribe(*channels)
                self._listening = True
                logger.info(f"EventBus listening on: {channels}")

                for message in pubsub.listen():
                    if message["type"] == "message":
                        self._handle_message(message)
            except Exception as e:
                logger.error(f"EventBus listener crashed: {e}")
                self._listening = False

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()

    def _handle_message(self, message):
        """Handle incoming message from Redis."""
        try:
            data = json.loads(message["data"])
            event_type = data["event_type"]
            # We pass the full data (including payload) to the handler
            # Handlers expect the 'payload' dict usually, or the full envelope?
            # Spec says "Handler processes messages".
            # Let's pass the full envelope so they have metadata if needed.

            # Actually, looking at listeners.py example:
            # user_id = event['payload']['user_id']
            # So passing the whole data dict is correct.

            if event_type in self._subscribers:
                for handler in self._subscribers[event_type]:
                    try:
                        handler(data)
                    except Exception as e:
                        logger.error(f"Handler error for {event_type}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to process message: {str(e)}")


# Singleton instance
_event_bus_instance = None


def get_event_bus() -> EventBus:
    """Get singleton event bus instance."""
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = RedisEventBus()
    return _event_bus_instance
