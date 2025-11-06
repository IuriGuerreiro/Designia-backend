import logging
from typing import Any, Dict, List

from django.db import transaction

from ..models import Product

logger = logging.getLogger(__name__)


def create_product(user, validated_data: Dict[str, Any]) -> Product:
    """Create a Product owned by user from validated serializer data.

    This function encapsulates model creation rules and is easy to test.
    The caller remains responsible for file uploads and response shaping.
    """
    with transaction.atomic():
        product = Product.objects.create(seller=user, **validated_data)
        logger.info("Created product %s for user %s", product.id, getattr(user, "id", None))
        return product


def attach_uploaded_images(product: Product, uploaded_images: List[Dict[str, Any]]) -> None:
    """Optional helper to persist metadata or perform post-processing.

    Keep minimal for now; extend as we migrate upload logic.
    """
    # Placeholder for future hooks (e.g., metrics init, audit logs)
    logger.debug("Attached %d images to product %s", len(uploaded_images), product.id)
