import logging
from typing import Optional

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from .models import Chat, Message


logger = logging.getLogger(__name__)
User = get_user_model()


class UnreadMessageTracker:
    """
    Async utility for tracking unread message counts without blocking operations.
    Provides fire-and-forget async operations for WebSocket notifications.
    """

    @staticmethod
    @database_sync_to_async
    def get_user_unread_count(user_id: int) -> int:
        """
        Get total unread messages count for a user across all chats.

        Args:
            user_id: User ID to get unread count for

        Returns:
            int: Total unread messages count
        """
        try:
            from django.db import models

            user = User.objects.get(id=user_id)

            # Get all chats where user is participant
            user_chats = Chat.objects.filter(models.Q(user1=user) | models.Q(user2=user)).values_list("id", flat=True)

            # Count unread messages in all user's chats (excluding own messages)
            unread_count = (
                Message.objects.filter(chat_id__in=user_chats, is_read=False)
                .exclude(sender=user)  # Exclude own messages
                .count()
            )

            return unread_count

        except User.DoesNotExist:
            logger.warning(f"User {user_id} not found when getting unread count")
            return 0
        except Exception as e:
            logger.error(f"Error getting unread count for user {user_id}: {str(e)}")
            return 0

    @staticmethod
    @database_sync_to_async
    def mark_messages_read(chat_id: int, user_id: int, message_ids: Optional[list] = None) -> int:
        """
        Mark messages as read for a user in a chat.

        Args:
            chat_id: Chat ID where messages should be marked read
            user_id: User ID who read the messages
            message_ids: Optional list of specific message IDs to mark read

        Returns:
            int: Number of messages marked as read
        """
        try:
            from django.utils import timezone

            user = User.objects.get(id=user_id)
            chat = Chat.objects.get(id=chat_id)

            # Verify user is part of this chat
            if not chat.has_user(user):
                logger.warning(f"User {user_id} attempted to mark messages read in chat {chat_id} they're not part of")
                return 0

            # Build query for messages to mark read
            messages_query = Message.objects.filter(chat=chat, is_read=False).exclude(
                sender=user  # Don't mark own messages as read
            )

            # Filter by specific message IDs if provided
            if message_ids:
                messages_query = messages_query.filter(id__in=message_ids)

            # Update messages
            updated_count = messages_query.update(is_read=True, read_at=timezone.now())

            logger.info(f"Marked {updated_count} messages as read for user {user_id} in chat {chat_id}")
            return updated_count

        except (User.DoesNotExist, Chat.DoesNotExist) as e:
            logger.warning(f"Invalid user {user_id} or chat {chat_id}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(f"Error marking messages read for user {user_id} in chat {chat_id}: {str(e)}")
            return 0

    @classmethod
    async def notify_unread_count_change(cls, user_id: int):
        """
        Async fire-and-forget method to notify user of unread count change via ActivityConsumer.
        This method doesn't block and errors are logged but don't propagate.

        Args:
            user_id: User ID to notify
        """
        try:
            # Import here to avoid circular imports
            from activity.consumer import ActivityConsumer

            # Get updated unread count
            unread_count = await cls.get_user_unread_count(user_id)

            # Send notification via ActivityConsumer (fire-and-forget)
            await ActivityConsumer.notify_unread_count_update(user_id=user_id, unread_count=unread_count)

            logger.info(f"Notified user {user_id} of unread count: {unread_count}")

        except Exception as e:
            # Log error but don't raise - this is fire-and-forget
            logger.error(f"Failed to notify unread count change for user {user_id}: {str(e)}")

    @classmethod
    def notify_unread_count_change_async(cls, user_id: int):
        """
        Synchronous method that schedules async notification without waiting.
        Use this from sync contexts when you don't want to block.

        Args:
            user_id: User ID to notify
        """
        try:
            # Use Django's async_to_sync to properly handle the async call from sync context
            from asgiref.sync import async_to_sync

            async_to_sync(cls.notify_unread_count_change)(user_id)
        except Exception as e:
            # Log error but don't raise - this is fire-and-forget
            logger.error(f"Failed to schedule unread count notification for user {user_id}: {str(e)}")

    @classmethod
    async def handle_message_created(cls, message_id: int):
        """
        Handle new message creation - notify relevant users of count change.

        Args:
            message_id: ID of the newly created message
        """
        try:
            # Get message details
            message = await database_sync_to_async(
                lambda: Message.objects.select_related("chat", "sender").get(id=message_id)
            )()

            chat = message.chat
            sender = message.sender

            # Notify the recipient (other user in chat) of unread count change
            recipient = chat.get_other_user(sender)

            # Fire-and-forget notification
            await cls.notify_unread_count_change(recipient.id)

        except Message.DoesNotExist:
            logger.warning(f"Message {message_id} not found for unread notification")
        except Exception as e:
            logger.error(f"Error handling message creation for unread tracking: {str(e)}")

    @classmethod
    async def handle_messages_read(cls, chat_id: int, user_id: int, message_ids: Optional[list] = None):
        """
        Handle messages being marked as read - update counts and notify.

        Args:
            chat_id: Chat ID where messages were read
            user_id: User ID who read the messages
            message_ids: Optional specific message IDs that were read
        """
        try:
            # Mark messages as read
            updated_count = await cls.mark_messages_read(chat_id, user_id, message_ids)

            if updated_count > 0:
                # Notify user of updated unread count
                await cls.notify_unread_count_change(user_id)

        except Exception as e:
            logger.error(f"Error handling messages read: {str(e)}")
