from rest_framework import serializers

from chat.domain.models import ChatReport


class ChatReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatReport
        fields = [
            "id",
            "message",
            "reporter",
            "reason",
            "description",
            "created_at",
            "resolved",
        ]
        read_only_fields = ["id", "reporter", "created_at", "resolved"]
