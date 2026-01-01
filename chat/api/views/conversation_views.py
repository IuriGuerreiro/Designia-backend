from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from chat.api.serializers.conversation_serializers import (
    StartConversationSerializer,
    ThreadMessageSerializer,
    ThreadSerializer,
)
from chat.domain.models import Thread, ThreadParticipant


class MessagePagination(PageNumberPagination):
    """Pagination for chat messages"""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ThreadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return threads where current user is a participant
        return Thread.objects.filter(participants=self.request.user).distinct()

    def get_paginator(self):
        # Only paginate the messages action, not the conversation list
        if self.action == "messages":
            return super().get_paginator()
        return None

    @property
    def paginator(self):
        # Only paginate the messages action, not the conversation list
        if self.action == "messages":
            if not hasattr(self, "_paginator"):
                self._paginator = MessagePagination()
            return self._paginator
        return None

    def create(self, request, *args, **kwargs):
        """
        POST /api/chat/conversations/
        Body: { "product_id": "uuid" }
        """
        serializer = StartConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product_id"]
        seller = product.seller

        if seller == request.user:
            return Response(
                {"error": "You cannot start a conversation with yourself (you are the seller)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Look for an existing 1-on-1 thread between these two users
        # 1. Find threads the current user is part of
        user_threads = ThreadParticipant.objects.filter(user=request.user).values_list("thread_id", flat=True)

        # 2. Find threads the seller is part of, restricted to the user's threads
        # This gives us threads where BOTH are participants
        common_threads = ThreadParticipant.objects.filter(user=seller, thread_id__in=user_threads).values_list(
            "thread_id", flat=True
        )

        # 3. Find a non-group thread from these common IDs
        thread = Thread.objects.filter(id__in=common_threads, is_group=False).first()

        is_new = False

        if not thread:
            # Create new thread
            thread = Thread.objects.create(is_group=False)
            ThreadParticipant.objects.create(thread=thread, user=request.user)
            ThreadParticipant.objects.create(thread=thread, user=seller)
            is_new = True

            # Optional: Send a system message or link to product?
            # For now just return the thread ID

        return Response(
            {"thread_id": str(thread.id), "is_new": is_new},
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        thread = self.get_object()
        messages = thread.messages.all().order_by("-created_at")
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = ThreadMessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ThreadMessageSerializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """
        Mark all messages in the thread as read.
        """
        from chat.domain.services.chat_service import ChatService

        service = ChatService()
        try:
            count = service.mark_messages_as_read(request.user, pk)
            return Response({"marked_read": count}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
