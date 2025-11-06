from django.urls import re_path

from activity.consumer import ActivityConsumer

from .user_consumer import UserConsumer

websocket_urlpatterns = [
    # Activity WebSocket for cart events and notifications
    re_path(r"ws/activity/$", ActivityConsumer.as_asgi()),
    # Chat WebSocket for messaging only
    re_path(r"ws/chat/user/$", UserConsumer.as_asgi()),
]
