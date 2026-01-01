import logging

import redis
from asgiref.sync import sync_to_async
from django.conf import settings


logger = logging.getLogger(__name__)


class ChannelThrottlingMiddleware:
    """
    Middleware to throttle WebSocket connection attempts per IP address.
    Uses Redis to track connection counts.
    """

    def __init__(self, inner):
        self.inner = inner
        # Extract Redis URL from settings
        channel_layers = getattr(settings, "CHANNEL_LAYERS", {})
        default_config = channel_layers.get("default", {}).get("CONFIG", {})
        hosts = default_config.get("hosts", ["redis://localhost:6379/2"])

        # Use the first host defined
        self.redis_url = hosts[0] if isinstance(hosts, list) else hosts
        self._redis_client = None

    @property
    def redis(self):
        if self._redis_client is None:
            self._redis_client = redis.from_url(self.redis_url)
        return self._redis_client

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            # Get client IP
            client = scope.get("client")
            if client:
                ip = client[0]
                allowed = await self.is_allowed(ip)
                if not allowed:
                    logger.warning(f"WebSocket connection throttled for IP: {ip}")
                    # 4029 is a custom code often used for "Too Many Requests" in WS
                    await send(
                        {
                            "type": "websocket.close",
                            "code": 4029,
                        }
                    )
                    return

        return await self.inner(scope, receive, send)

    async def is_allowed(self, ip: str) -> bool:
        """
        Check if the IP is allowed to connect based on rate limits.
        """
        # Fixed window counter: 60 connects per minute
        key = f"ws_throttle:{ip}"
        limit = 60
        window = 60  # seconds

        # We use sync_to_async for redis calls to avoid blocking the event loop
        # since we are using the sync redis client.
        return await sync_to_async(self._check_redis)(key, limit, window)

    def _check_redis(self, key, limit, window):
        try:
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window, nx=True)  # Only set expiry if it doesn't exist
            results = pipe.execute()
            count = results[0]
            return count <= limit
        except Exception as e:
            logger.error(f"Error checking WS throttle in Redis: {str(e)}")
            # Fail open to avoid blocking users if Redis is down
            return True
