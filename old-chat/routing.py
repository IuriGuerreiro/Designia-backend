from django.urls import re_path

from activity.consumer import ActivityConsumer

from . import consumers
from .user_consumer import UserConsumer


websocket_urlpatterns = [
    # Activity WebSocket for cart events and notifications
    re_path(r"ws/activity/$", ActivityConsumer.as_asgi()),
    # Chat WebSocket for messaging only (simplified from user_consumer)
    re_path(r"ws/chat/user/$", UserConsumer.as_asgi()),
    # Individual chat WebSocket for backward compatibility
    re_path(r"ws/chat/(?P<chat_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
]
