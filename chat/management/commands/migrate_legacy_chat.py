from django.core.management.base import BaseCommand
from django.db import transaction

from chat.domain.models import Thread, ThreadMessage, ThreadParticipant
from chat.models import Chat


class Command(BaseCommand):
    help = "Migrates legacy Chat/Message data to new Thread/ThreadMessage models"

    def handle(self, *args, **options):
        self.stdout.write("Starting legacy chat migration...")

        legacy_chats = Chat.objects.all()
        count = legacy_chats.count()
        self.stdout.write(f"Found {count} legacy chats to migrate.")

        migrated_threads = 0
        migrated_messages = 0

        # We need to manually set created_at for Thread and ThreadMessage
        # because auto_now_add ignores the value passed to create()

        with transaction.atomic():
            for chat in legacy_chats:
                # 1. Create Thread
                thread = Thread.objects.create(updated_at=chat.updated_at, is_group=False)
                # Force update created_at
                thread.created_at = chat.created_at
                thread.save(update_fields=["created_at"])

                # 2. Create Participants
                ThreadParticipant.objects.create(thread=thread, user=chat.user1, joined_at=chat.created_at)
                ThreadParticipant.objects.create(thread=thread, user=chat.user2, joined_at=chat.created_at)

                # 3. Migrate Messages
                legacy_messages = chat.messages.all()
                new_messages = []
                for msg in legacy_messages:
                    new_msg = ThreadMessage(
                        thread=thread,
                        sender=msg.sender,
                        message_type=msg.message_type,
                        text=msg.text_content,
                        image_url=msg.image_url,
                        is_read=msg.is_read,
                    )
                    # We set created_at on the instance, but save() might override it due to auto_now_add=True
                    # So we have to save first, then update, OR use bulk_create which respects it if we are careful?
                    # Actually, bulk_create usually DOES respect custom values for auto_now_add fields
                    # unlike save(). Let's try bulk_create for messages for speed.
                    new_msg.created_at = msg.created_at
                    new_messages.append(new_msg)

                if new_messages:
                    ThreadMessage.objects.bulk_create(new_messages)
                    migrated_messages += len(new_messages)

                migrated_threads += 1

                if migrated_threads % 100 == 0:
                    self.stdout.write(f"Migrated {migrated_threads} chats...")

        self.stdout.write(
            self.style.SUCCESS(f"Migration complete! Threads: {migrated_threads}, Messages: {migrated_messages}")
        )
