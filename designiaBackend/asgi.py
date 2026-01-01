"""
ASGI config for designiaBackend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https:docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

import django
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application


# Set the correct settings module to the consolidated settings file
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "designiaBackend.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django.setup()

django_asgi_app = get_asgi_application()

# Import routing here, after Django has been initialized
import chat.routing  # noqa: E402
from chat.middleware import ChannelThrottlingMiddleware  # noqa: E402


application = ProtocolTypeRouter(
    {
        # Django's ASGI application to handle traditional HTTP requests
        "http": django_asgi_app,
        # WebSocket chat application with authentication and throttling
        "websocket": ChannelThrottlingMiddleware(
            AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns)))
        ),
    }
)
