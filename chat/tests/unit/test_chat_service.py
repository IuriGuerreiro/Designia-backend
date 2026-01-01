from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from chat.domain.models import Thread, ThreadMessage, ThreadParticipant
from chat.domain.services.chat_service import ChatService


User = get_user_model()


class ChatServiceTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="u1", email="u1@example.com", password="pw")
        self.user2 = User.objects.create_user(username="u2", email="u2@example.com", password="pw")
        self.outsider = User.objects.create_user(username="out", email="out@example.com", password="pw")

        self.thread = Thread.objects.create()
        ThreadParticipant.objects.create(thread=self.thread, user=self.user1)
        ThreadParticipant.objects.create(thread=self.thread, user=self.user2)

        self.service = ChatService()

    @patch("chat.domain.services.chat_service.async_to_sync")
    def test_send_message_success(self, mock_async_to_sync):
        # Mock channel layer on the instance
        mock_layer = MagicMock()
        self.service.channel_layer = mock_layer

        # Configure async_to_sync to return a wrapper that calls the mock
        # async_to_sync(func)(*args) -> so mock_async_to_sync(func) returns a callable
        mock_executor = MagicMock()
        mock_async_to_sync.return_value = mock_executor

        msg = self.service.send_message(self.user1, self.thread.id, "Hello")

        # Check DB
        self.assertEqual(ThreadMessage.objects.count(), 1)
        self.assertEqual(msg.text, "Hello")
        self.assertEqual(msg.sender, self.user1)

        # Check Broadcast
        # async_to_sync should be called with group_send
        mock_async_to_sync.assert_called_with(mock_layer.group_send)
        # The result of async_to_sync (mock_executor) should be called with args
        mock_executor.assert_called_once()
        args, kwargs = mock_executor.call_args
        self.assertEqual(args[0], f"thread_{self.thread.id}")
        self.assertEqual(args[1]["type"], "chat_message")

    def test_send_message_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            self.service.send_message(self.outsider, self.thread.id, "Intruder")

    def test_get_history_pagination(self):
        # Create 25 messages
        for i in range(25):
            ThreadMessage.objects.create(thread=self.thread, sender=self.user1, text=f"Msg {i}")

        page1 = self.service.get_conversation_history(self.user1, self.thread.id, page=1, page_size=10)
        self.assertEqual(len(page1), 10)

        page2 = self.service.get_conversation_history(self.user1, self.thread.id, page=2, page_size=10)
        self.assertEqual(len(page2), 10)

        page3 = self.service.get_conversation_history(self.user1, self.thread.id, page=3, page_size=10)
        self.assertEqual(len(page3), 5)

    def test_get_history_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            self.service.get_conversation_history(self.outsider, self.thread.id)
