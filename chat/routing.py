from django.urls import re_path
from . import consumers
from .user_consumer import UserConsumer

websocket_urlpatterns = [
    # Global user WebSocket for all chats
    re_path(r'ws/user/$', UserConsumer.as_asgi()),
    # Keep individual chat WebSocket for backward compatibility
    re_path(r'ws/chat/(?P<chat_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
]