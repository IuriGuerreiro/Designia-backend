from django.urls import re_path

from activity.consumer import ActivityConsumer
from chat.api.consumers import ChatConsumer


websocket_urlpatterns = [
    re_path(r"ws/activity/$", ActivityConsumer.as_asgi()),
    re_path(r"ws/chat/(?P<thread_id>[0-9a-f-]+)/$", ChatConsumer.as_asgi()),
]
