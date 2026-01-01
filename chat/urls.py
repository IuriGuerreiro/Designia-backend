from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .api.views.conversation_views import ConversationViewSet
from .api.views.report_views import ReportViewSet


router = DefaultRouter()
router.register(r"conversations", ConversationViewSet, basename="conversation")
router.register(r"reports", ReportViewSet, basename="chat-report")

urlpatterns = [
    # New Refactored API
    path("", include(router.urls)),
    # Chat endpoints
    path("", views.ChatListView.as_view(), name="chat_list"),
    path("<int:pk>/", views.ChatDetailView.as_view(), name="chat_detail"),
    # Message endpoints
    path("<int:chat_id>/messages/", views.MessageListView.as_view(), name="message_list"),
    path("<int:chat_id>/messages/mark-read/", views.mark_messages_read, name="mark_messages_read"),
    # Image upload
    path("upload-image/", views.upload_chat_image, name="upload_chat_image"),
    # User search
    path("search-users/", views.search_users, name="search_users"),
]
