from rest_framework import serializers

from .models import CustomUser
from .seller_models import SellerApplication, SellerApplicationImage


class SellerApplicationImageSerializer(serializers.ModelSerializer):
    """Serializer for seller application images"""

    class Meta:
        model = SellerApplicationImage
        fields = ["id", "image", "image_type", "description", "order", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]


class SellerApplicationSerializer(serializers.ModelSerializer):
    """Serializer for seller applications"""

    images = SellerApplicationImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(max_length=100000, allow_empty_file=False, use_url=False),
        write_only=True,
        required=False,
    )
    image_descriptions = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=True), write_only=True, required=False
    )
    image_types = serializers.ListField(
        child=serializers.ChoiceField(choices=SellerApplicationImage.IMAGE_TYPE_CHOICES),
        write_only=True,
        required=False,
    )

    # Read-only fields for admin info
    approved_by_name = serializers.CharField(source="approved_by.get_full_name", read_only=True)
    rejected_by_name = serializers.CharField(source="rejected_by.get_full_name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = SellerApplication
        fields = [
            "id",
            "user",
            "business_name",
            "seller_type",
            "motivation",
            "portfolio_url",
            "social_media_url",
            "status",
            "admin_notes",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "approved_by",
            "rejected_by",
            "approved_by_name",
            "rejected_by_name",
            "user_email",
            "user_name",
            "images",
            "uploaded_images",
            "image_descriptions",
            "image_types",
        ]
        read_only_fields = [
            "id",
            "status",
            "admin_notes",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "approved_by",
            "rejected_by",
        ]

    def create(self, validated_data):
        import logging

        logger = logging.getLogger(__name__)

        logger.info("=== SERIALIZER CREATE DEBUG ===")
        logger.info(f"Validated data keys: {list(validated_data.keys())}")
        logger.info(f"User in validated_data: {validated_data.get('user', 'NOT_FOUND')}")

        # Remove image-related data from validated_data
        uploaded_images = validated_data.pop("uploaded_images", [])
        image_descriptions = validated_data.pop("image_descriptions", [])
        image_types = validated_data.pop("image_types", [])

        logger.info(f"Final validated_data for creation: {validated_data}")

        # Create the application
        application = SellerApplication.objects.create(**validated_data)
        logger.info(f"✓ Application created with ID: {application.id}, User: {application.user}")

        # Handle image uploads
        self._create_images(application, uploaded_images, image_descriptions, image_types)

        return application

    def _create_images(self, application, uploaded_images, descriptions, types):
        """Create application images"""
        for index, image in enumerate(uploaded_images):
            description = descriptions[index] if index < len(descriptions) else ""
            image_type = types[index] if index < len(types) else "workshop"

            SellerApplicationImage.objects.create(
                application=application, image=image, image_type=image_type, description=description, order=index
            )


class SellerApplicationAdminSerializer(serializers.ModelSerializer):
    """Serializer for admin actions on seller applications"""

    class Meta:
        model = SellerApplication
        fields = ["status", "admin_notes", "rejection_reason"]

    def update(self, instance, validated_data):
        admin_user = self.context["request"].user
        status = validated_data.get("status")

        if status == "approved":
            instance.approve_application(admin_user)
        elif status == "rejected":
            reason = validated_data.get("rejection_reason", "")
            instance.reject_application(admin_user, reason)
        elif status == "revision_requested":
            notes = validated_data.get("admin_notes", "")
            instance.request_revision(admin_user, notes)
        else:
            # For other status updates
            instance.status = status
            instance.admin_notes = validated_data.get("admin_notes", instance.admin_notes)
            instance.save()

        return instance


class UserRoleSerializer(serializers.ModelSerializer):
    """Serializer for user role information"""

    class Meta:
        model = CustomUser
        fields = ["id", "email", "first_name", "last_name", "role"]
        read_only_fields = ["id", "email", "first_name", "last_name"]
