from django.contrib.auth import get_user_model
from rest_framework import serializers


User = get_user_model()


class MinimalSellerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]
        read_only_fields = ["id"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "avatar"]
        read_only_fields = ["id"]
