"""
ARService - Augmented Reality Logic

Handles 3D model management, validation, and URL generation for AR features.

Story 5.5: Extract AR Logic to ARService
"""

import logging
import os
from typing import Dict, Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from ar.models import ProductARModel
from marketplace.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok

logger = logging.getLogger(__name__)


class ARService(BaseService):
    """
    Service for managing Augmented Reality assets (3D models).

    Responsibilities:
    - 3D Model validation (size, format)
    - Upload/Storage management (via S3/MinIO)
    - URL generation (Proxy/Presigned)
    - Metadata management
    """

    ALLOWED_EXTENSIONS = {".glb", ".gltf", ".usdz"}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB default

    def __init__(self):
        super().__init__()
        self.max_size = getattr(settings, "AR_MODEL_MAX_SIZE", self.MAX_FILE_SIZE)

    @BaseService.log_performance
    def has_3d_model(self, product_id: str) -> ServiceResult[bool]:
        """
        Check if a product has an associated 3D model.

        Args:
            product_id: Product UUID

        Returns:
            ServiceResult with boolean
        """
        try:
            # Check for existence of related ProductARModel
            exists = ProductARModel.objects.filter(product_id=product_id).exists()
            return service_ok(exists)
        except Exception as e:
            self.logger.error(f"Error checking AR model existence for {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_ar_view_url(self, product_id: str) -> ServiceResult[Optional[str]]:
        """
        Get the URL to view/download the 3D model.

        Args:
            product_id: Product UUID

        Returns:
            ServiceResult with URL string or None
        """
        try:
            ar_model = ProductARModel.objects.filter(product_id=product_id).first()
            if not ar_model:
                return service_ok(None)

            # Generate proxy URL to avoid mixed content and hide bucket details
            # Similar to ProductImage.get_proxy_url
            if ar_model.s3_key:
                # Assuming a consistent proxy endpoint structure
                # In a real scenario, we might use reverse() but keeping it simple for service
                url = f"/api/system/s3-models/{ar_model.s3_key}"
                return service_ok(url)

            return service_ok(None)

        except Exception as e:
            self.logger.error(f"Error getting AR view URL for {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    def validate_3d_model_file(self, file: UploadedFile) -> ServiceResult[bool]:
        """
        Validate a 3D model file before upload.

        Checks:
        - File size
        - Extension

        Args:
            file: UploadedFile object

        Returns:
            ServiceResult with boolean (True if valid) or error
        """
        try:
            # Check size
            if file.size > self.max_size:
                return service_err(
                    ErrorCodes.INVALID_INPUT, f"File size {file.size} exceeds limit of {self.max_size} bytes"
                )

            # Check extension
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                return service_err(
                    ErrorCodes.INVALID_INPUT,
                    f"Invalid file format '{ext}'. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}",
                )

            return service_ok(True)

        except Exception as e:
            self.logger.error(f"Error validating 3D model file: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_model_metadata(self, product_id: str) -> ServiceResult[Dict]:
        """
        Get metadata for the product's 3D model.

        Includes file size, content type, upload timestamp, and access URL.

        Args:
            product_id: Product UUID

        Returns:
            ServiceResult with metadata dict containing:
            - id: AR model ID
            - file_size: Size in bytes
            - content_type: MIME type
            - uploaded_at: Timestamp
            - original_filename: Original file name
            - url: Access URL (proxy)
        """
        try:
            ar_model = ProductARModel.objects.filter(product_id=product_id).first()
            if not ar_model:
                return service_err(ErrorCodes.NOT_FOUND, "No AR model found for this product")

            data = {
                "id": ar_model.id,
                "file_size": ar_model.file_size,
                "content_type": ar_model.content_type,
                "uploaded_at": ar_model.uploaded_at,
                "original_filename": ar_model.original_filename,
                "url": self.get_ar_view_url(product_id).value,
            }
            return service_ok(data)

        except Exception as e:
            self.logger.error(f"Error getting AR metadata for {product_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
