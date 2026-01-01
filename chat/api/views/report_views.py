from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from chat.api.serializers.report_serializers import ChatReportSerializer
from chat.domain.models import ChatReport, ThreadMessage


class ReportViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = ChatReport.objects.all()
    serializer_class = ChatReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Verify message exists (redundant with serializer but good for explicit error)
        message_id = request.data.get("message")
        try:
            # Ensure the user has access to the message they are reporting?
            # Reporting usually implies they can see it.
            # We could check ThreadParticipant but the message ID is unique.
            ThreadMessage.objects.get(id=message_id)
        except ThreadMessage.DoesNotExist:
            return Response({"error": "Message not found"}, status=status.HTTP_404_NOT_FOUND)

        # Create report
        serializer.save(reporter=request.user)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
