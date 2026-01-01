from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from chat.api.consumers import ChatConsumer
from chat.domain.models import Thread, ThreadParticipant


User = get_user_model()


class ChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", email="test@test.com", password="pw")
        self.thread = Thread.objects.create()
        ThreadParticipant.objects.create(thread=self.thread, user=self.user)

    async def test_connect_success(self):
        # We must manually construct the scope that the router would normally provide
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.thread.id}/")
        # Mock authenticated user
        communicator.scope["user"] = self.user
        communicator.scope["url_route"] = {"kwargs": {"thread_id": str(self.thread.id)}}

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_connect_denied_not_participant(self):
        other_thread = await database_sync_to_async(Thread.objects.create)()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{other_thread.id}/")
        communicator.scope["user"] = self.user
        communicator.scope["url_route"] = {"kwargs": {"thread_id": str(other_thread.id)}}

        connected, subprotocol = await communicator.connect()
        self.assertFalse(connected)
        # The second return value of connect() contains the close code when connection fails
        self.assertEqual(subprotocol, 4003)

    async def test_send_receive_message(self):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.thread.id}/")
        communicator.scope["user"] = self.user
        communicator.scope["url_route"] = {"kwargs": {"thread_id": str(self.thread.id)}}

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Send message
        payload = {"type": "chat.message", "payload": {"text": "Hello Integration"}}
        await communicator.send_json_to(payload)

        # Receive broadcast (Echo)
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "chat.message")
        self.assertEqual(response["data"]["text"], "Hello Integration")
        self.assertEqual(response["data"]["sender_id"], str(self.user.id))

        await communicator.disconnect()
