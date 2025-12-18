from rest_framework import serializers

from marketplace.ordering.domain.models import Order, OrderItem, ReturnRequest


class ReturnRequestCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a return request.
    Validates items to ensure they belong to the order and quantities are valid.
    """

    order_items = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField(),  # Expecting {'item_id': int, 'quantity': int}
        ),
        min_length=1,
        error_messages={"empty": "Please select at least one item to return."},
    )
    reason = serializers.ChoiceField(
        choices=ReturnRequest.RETURN_REASON_CHOICES, error_messages={"invalid_choice": "Invalid return reason."}
    )
    comment = serializers.CharField(required=False, allow_blank=True)
    proof_image_urls = serializers.ListField(child=serializers.URLField(), required=False, allow_empty=True)

    def validate(self, data):
        """
        Validate that requested order_items belong to the order and quantities are valid.
        """
        order_id = self.context.get("order_id")
        if not order_id:
            raise serializers.ValidationError("Order ID must be provided in the context.")

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found.")

        valid_order_item_ids = set(order.items.values_list("id", flat=True))

        # Validate that all requested items are part of the order and quantities are not excessive
        validated_items_data = []
        for item_data in data["order_items"]:
            item_id = item_data.get("itemId")  # Frontend sends itemId
            quantity = item_data.get("quantity")

            if item_id not in valid_order_item_ids:
                raise serializers.ValidationError(f"Item with ID {item_id} does not belong to this order.")

            # Find the actual OrderItem to compare quantities
            try:
                order_item = order.items.get(id=item_id)
            except OrderItem.DoesNotExist:
                raise serializers.ValidationError(f"Order item with ID {item_id} not found in this order.")

            if not isinstance(quantity, int) or quantity <= 0 or quantity > order_item.quantity:
                raise serializers.ValidationError(
                    f"Invalid quantity {quantity} for item {item_id}. Must be between 1 and {order_item.quantity}."
                )

            validated_items_data.append({"order_item": order_item, "quantity": quantity})

        data["validated_order"] = order
        data["validated_order_items"] = validated_items_data  # Store validated items for later use
        return data


class ReturnRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for the ReturnRequest model (output/read-only).
    """

    order_id = serializers.UUIDField(source="order.id", read_only=True)
    requested_by_username = serializers.CharField(source="requested_by.username", read_only=True)

    # You might want to include the specific items that were returned in the response
    # For now, it's captured in the main ReturnRequest object.

    class Meta:
        model = ReturnRequest
        fields = [
            "id",
            "order_id",
            "requested_by_username",
            "reason",
            "comment",
            "status",
            "proof_image_urls",
            "created_at",
            "updated_at",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]
        read_only_fields = [
            "id",
            "order_id",
            "requested_by_username",
            "status",
            "created_at",
            "updated_at",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]
