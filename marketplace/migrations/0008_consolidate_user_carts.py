# Generated manually for cart consolidation

import logging

from django.db import migrations
from django.db.models import Count

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


def consolidate_carts(apps, schema_editor):
    """
    Consolidate multiple carts per user into a single cart.
    Keep the most recent cart with items, or the most recent cart if none have items.
    """
    Cart = apps.get_model("marketplace", "Cart")
    CartItem = apps.get_model("marketplace", "CartItem")

    # Find users with multiple carts
    users_with_multiple_carts = Cart.objects.values("user").annotate(cart_count=Count("user")).filter(cart_count__gt=1)

    for user_data in users_with_multiple_carts:
        user_id = user_data["user"]
        user_carts = Cart.objects.filter(user_id=user_id).order_by("-created_at")

        # Find the best cart to keep (prioritize carts with items)
        cart_to_keep = None

        # First, try to find a cart with items
        for cart in user_carts:
            if CartItem.objects.filter(cart=cart).exists():
                cart_to_keep = cart
                break

        # If no cart has items, keep the most recent one
        if not cart_to_keep:
            cart_to_keep = user_carts.first()

        # Merge items from other carts into the cart we're keeping
        for cart in user_carts:
            if cart.id != cart_to_keep.id:
                # Move all items from this cart to the cart we're keeping
                CartItem.objects.filter(cart=cart).update(cart=cart_to_keep)
                # Delete the empty cart
                cart.delete()

        logger.info(f"Consolidated carts for user {user_id}, keeping cart {cart_to_keep.id}")


def reverse_consolidate_carts(apps, schema_editor):
    """
    This migration cannot be reversed as we've lost data about which
    cart items originally belonged to which carts.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0007_alter_cart_user"),
    ]

    operations = [
        migrations.RunPython(consolidate_carts, reverse_consolidate_carts),
    ]
