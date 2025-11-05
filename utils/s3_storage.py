"""
S3 Storage Utility Module for Desginia Marketplace

This module provides a comprehensive interface for AWS S3 operations including
file upload, download, deletion, and listing. It integrates with Django settings
and provides helper methods for common marketplace file operations.

Author: AI IDE Agent
Created: 2025-08-21
"""

import logging
import mimetypes
import os
from io import BytesIO
from typing import Any, Dict, List, Optional, Union

import boto3
import magic
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, NoCredentialsError
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.utils import timezone

logger = logging.getLogger(__name__)


class S3StorageError(Exception):
    """Custom exception for S3 storage operations"""

    pass


class S3Storage:
    """
    Comprehensive S3 storage utility class for file operations.

    Provides methods for uploading, downloading, deleting, and managing
    files in AWS S3 with proper error handling and marketplace-specific
    helper methods.
    """

    def __init__(self):
        """Initialize S3 client with configuration validation"""
        self._validate_configuration()
        self._initialize_client()

    def _validate_configuration(self) -> None:
        """Validate S3 configuration from Django settings"""
        if not getattr(settings, "USE_S3", False):
            raise S3StorageError("S3 storage is not enabled. Set USE_S3=True in settings.")

        required_settings = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_STORAGE_BUCKET_NAME",
        ]

        missing_settings = []
        for setting in required_settings:
            if not getattr(settings, setting, None):
                missing_settings.append(setting)

        if missing_settings:
            raise S3StorageError(f"Missing required S3 settings: {', '.join(missing_settings)}")

    def _initialize_client(self) -> None:
        """Initialize boto3 S3 client with error handling"""
        try:
            endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
            signature_version = getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4")
            addressing_style = getattr(settings, "AWS_S3_ADDRESSING_STYLE", "path")

            config = BotoConfig(signature_version=signature_version, s3={"addressing_style": addressing_style})

            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
                endpoint_url=endpoint_url,
                config=config,
                verify=getattr(settings, "AWS_S3_VERIFY", True),
            )

            self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            self.region = getattr(settings, "AWS_S3_REGION_NAME", "us-east-1")
            self.endpoint_url = endpoint_url

            # Test connection
            self._test_connection()

        except NoCredentialsError as e:
            raise S3StorageError("AWS credentials not found or invalid") from e
        except Exception as e:
            raise S3StorageError(f"Failed to initialize S3 client: {str(e)}") from e

    def _test_connection(self) -> None:
        """Test S3 connection and bucket access"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully connected to S3 bucket: {self.bucket_name}")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                raise S3StorageError(f"S3 bucket '{self.bucket_name}' not found") from e
            elif error_code == "403":
                raise S3StorageError(f"Access denied to S3 bucket '{self.bucket_name}'") from e
            else:
                raise S3StorageError(f"Error accessing S3 bucket: {str(e)}") from e

    def _get_content_type(self, file_name: str) -> str:
        """Get content type for file based on extension"""
        content_type, _ = mimetypes.guess_type(file_name)
        return content_type or "application/octet-stream"

    def _validate_image_file(  # noqa: C901
        self, file_obj: Union[InMemoryUploadedFile, TemporaryUploadedFile, BytesIO], file_name: str
    ) -> Dict[str, Any]:
        """
        Validate image file for security and format compliance.

        Args:
            file_obj: File object to validate
            file_name: Name of the file including extension

        Returns:
            Dict with validation results

        Raises:
            S3StorageError: If file validation fails
        """
        # Allowed image extensions (no GIF support)
        allowed_extensions = {"jpg", "jpeg", "png", "webp"}

        # Maximum file size (10MB)
        max_file_size = 10 * 1024 * 1024

        # Get file extension
        file_extension = file_name.lower().split(".")[-1] if "." in file_name else ""

        # Validate extension
        if not file_extension:
            raise S3StorageError("File must have an extension")

        if file_extension not in allowed_extensions:
            raise S3StorageError(
                f"File extension '{file_extension}' not allowed. "
                f"Allowed types: {', '.join(sorted(allowed_extensions))}"
            )

        # Get file size
        if hasattr(file_obj, "size"):
            file_size = file_obj.size
        elif hasattr(file_obj, "seek") and hasattr(file_obj, "tell"):
            # For BytesIO objects
            current_pos = file_obj.tell()
            file_obj.seek(0, 2)  # Seek to end
            file_size = file_obj.tell()
            file_obj.seek(current_pos)  # Reset position
        else:
            raise S3StorageError("Cannot determine file size")

        # Validate file size
        if file_size > max_file_size:
            raise S3StorageError(
                f"File size {file_size / 1024 / 1024:.1f}MB exceeds "
                f"maximum allowed size of {max_file_size / 1024 / 1024:.1f}MB"
            )

        # Validate MIME type using python-magic
        try:
            if hasattr(file_obj, "read"):
                # Read first 2048 bytes for magic detection
                current_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)

                magic_bytes = file_obj.read(2048)

                # Reset file position
                if hasattr(file_obj, "seek"):
                    file_obj.seek(current_pos)

                # Detect MIME type
                detected_mime = magic.from_buffer(magic_bytes, mime=True)

                # Validate MIME type matches extension
                valid_mime_types = {
                    "jpg": ["image/jpeg"],
                    "jpeg": ["image/jpeg"],
                    "png": ["image/png"],
                    "webp": ["image/webp"],
                }

                expected_mimes = valid_mime_types.get(file_extension, [])
                if expected_mimes and detected_mime not in expected_mimes:
                    raise S3StorageError(
                        f"File content type '{detected_mime}' doesn't match "
                        f"extension '.{file_extension}'. Expected: {', '.join(expected_mimes)}"
                    )

                # Block GIF files specifically (additional safety check)
                if detected_mime == "image/gif":
                    raise S3StorageError("GIF files are not allowed")

        except Exception as e:
            if isinstance(e, S3StorageError):
                raise
            logger.warning(f"Could not validate MIME type for {file_name}: {str(e)}")
            # Continue without MIME validation if magic fails

        return {
            "valid": True,
            "file_size": file_size,
            "extension": file_extension,
            "mime_type": getattr(file_obj, "content_type", None) or self._get_content_type(file_name),
        }

    def _validate_encoding_metadata(
        self, encoding: str, quality: float, original_size: int, encoded_size: int, compression_ratio: float
    ) -> Dict[str, Any]:
        """
        Validate image encoding metadata from frontend.

        Args:
            encoding: Image encoding format (jpeg, png, webp)
            quality: Compression quality (0.0-1.0)
            original_size: Original file size in bytes
            encoded_size: Encoded file size in bytes
            compression_ratio: Compression ratio (original/encoded)

        Returns:
            Dict with validation results

        Raises:
            S3StorageError: If metadata validation fails
        """
        # Validate encoding format
        allowed_encodings = {"jpeg", "png", "webp"}
        if encoding not in allowed_encodings:
            raise S3StorageError(f"Invalid encoding '{encoding}'. Allowed: {', '.join(allowed_encodings)}")

        # Validate quality range
        if not (0.0 <= quality <= 1.0):
            raise S3StorageError(f"Invalid quality {quality}. Must be between 0.0 and 1.0")

        # Validate file sizes
        max_file_size = 10 * 1024 * 1024  # 10MB
        if original_size > max_file_size:
            raise S3StorageError(
                f"Original file size {original_size / 1024 / 1024:.1f}MB exceeds maximum of {max_file_size / 1024 / 1024:.1f}MB"
            )

        if encoded_size > max_file_size:
            raise S3StorageError(
                f"Encoded file size {encoded_size / 1024 / 1024:.1f}MB exceeds maximum of {max_file_size / 1024 / 1024:.1f}MB"
            )

        # Validate compression ratio (should be >= 1.0, indicating compression occurred)
        if compression_ratio < 0.1:
            raise S3StorageError(f"Invalid compression ratio {compression_ratio}")

        # Validate that encoded size is reasonable
        if encoded_size > original_size * 1.1:  # Allow 10% increase for edge cases
            logger.warning(
                f"Encoded file size ({encoded_size}) larger than original ({original_size}). "
                f"Compression may have failed."
            )

        return {
            "valid": True,
            "encoding": encoding,
            "quality": quality,
            "original_size": original_size,
            "encoded_size": encoded_size,
            "compression_ratio": compression_ratio,
            "size_reduction_percent": ((original_size - encoded_size) / original_size) * 100,
        }

    def _get_file_size(self, file_obj: Union[InMemoryUploadedFile, TemporaryUploadedFile, BytesIO]) -> int:
        """Get file size from file object"""
        if hasattr(file_obj, "size") and file_obj.size is not None:
            return file_obj.size

        # For BytesIO or other file-like objects
        current_pos = file_obj.tell()
        file_obj.seek(0, 2)  # Seek to end
        size = file_obj.tell()
        file_obj.seek(current_pos)  # Restore position
        return size

    def upload_file(  # noqa: C901
        self,
        file_obj: Union[InMemoryUploadedFile, TemporaryUploadedFile, BytesIO, str],
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        public: bool = False,
        content_type: Optional[str] = None,
        validate_image: bool = True,
    ) -> Dict[str, Any]:
        """
        Upload a file to S3 bucket.

        Args:
            file_obj: File object or file path to upload
            key: S3 object key (path in bucket)
            metadata: Additional metadata for the file
            public: Whether to make the file publicly accessible
            content_type: Override content type detection
            validate_image: Whether to validate image files (default: True)

        Returns:
            Dict containing upload result information

        Raises:
            S3StorageError: If upload fails or validation fails
        """
        try:
            # Get file name from key for validation
            file_name = key.split("/")[-1]

            # Validate image files if requested
            if validate_image and isinstance(file_obj, (InMemoryUploadedFile, TemporaryUploadedFile, BytesIO)):
                validation_result = self._validate_image_file(file_obj, file_name)
                logger.info(f"File validation passed for {file_name}: {validation_result}")

            # Prepare upload parameters
            upload_params = {
                "Bucket": self.bucket_name,
                "Key": key,
            }

            # Handle different file object types
            if isinstance(file_obj, str):
                # File path
                if not os.path.exists(file_obj):
                    raise S3StorageError(f"File not found: {file_obj}")

                upload_params["Filename"] = file_obj
                file_size = os.path.getsize(file_obj)

                if not content_type:
                    content_type = self._get_content_type(file_obj)

            else:
                # File object
                upload_params["Fileobj"] = file_obj
                file_size = self._get_file_size(file_obj)

                if not content_type:
                    file_name = getattr(file_obj, "name", key)
                    content_type = self._get_content_type(file_name)

            # Set content type
            upload_params["ExtraArgs"] = {
                "ContentType": content_type,
            }

            # ACL removed - bucket does not allow ACLs
            # Files will be public based on bucket policy instead

            # Add metadata
            if metadata:
                upload_params["ExtraArgs"]["Metadata"] = metadata

            # Add cache control
            cache_control = getattr(settings, "AWS_S3_OBJECT_PARAMETERS", {}).get("CacheControl")
            if cache_control:
                upload_params["ExtraArgs"]["CacheControl"] = cache_control

            # Perform upload
            if "Filename" in upload_params:
                self.s3_client.upload_file(**upload_params)
            else:
                self.s3_client.upload_fileobj(**upload_params)

            # Generate file URL
            file_url = self.get_file_url(key, public=public)

            logger.info(f"Successfully uploaded file to S3: {key}")

            return {
                "success": True,
                "key": key,
                "url": file_url,
                "size": file_size,
                "content_type": content_type,
                "bucket": self.bucket_name,
                "uploaded_at": timezone.now().isoformat(),
            }

        except ClientError as e:
            error_msg = f"Failed to upload file to S3: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during upload: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e

    def download_file(self, key: str, download_path: Optional[str] = None) -> Union[bytes, bool]:
        """
        Download a file from S3 bucket.

        Args:
            key: S3 object key
            download_path: Local path to save file (if None, returns file content)

        Returns:
            File content as bytes if download_path is None, otherwise True

        Raises:
            S3StorageError: If download fails
        """
        try:
            if download_path:
                # Download to file
                self.s3_client.download_file(self.bucket_name, key, download_path)
                logger.info(f"Downloaded file from S3 to: {download_path}")
                return True
            else:
                # Download to memory
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                content = response["Body"].read()
                logger.info(f"Downloaded file content from S3: {key}")
                return content

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                raise S3StorageError(f"File not found in S3: {key}") from e
            else:
                error_msg = f"Failed to download file from S3: {str(e)}"
                logger.error(error_msg)
                raise S3StorageError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during download: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e

    def delete_file(self, key: str) -> bool:
        """
        Delete a file from S3 bucket.

        Args:
            key: S3 object key to delete

        Returns:
            True if successful

        Raises:
            S3StorageError: If deletion fails
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted file from S3: {key}")
            return True

        except ClientError as e:
            error_msg = f"Failed to delete file from S3: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during deletion: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e

    def list_files(
        self, prefix: str = "", max_keys: int = 1000, continuation_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List files in S3 bucket with optional prefix filtering.

        Args:
            prefix: Filter files by prefix
            max_keys: Maximum number of files to return
            continuation_token: Token for pagination

        Returns:
            Dict containing file list and pagination info

        Raises:
            S3StorageError: If listing fails
        """
        try:
            params = {
                "Bucket": self.bucket_name,
                "MaxKeys": max_keys,
            }

            if prefix:
                params["Prefix"] = prefix

            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = self.s3_client.list_objects_v2(**params)

            files = []
            if "Contents" in response:
                for obj in response["Contents"]:
                    files.append(
                        {
                            "key": obj["Key"],
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                            "etag": obj["ETag"].strip('"'),
                            "url": self.get_file_url(obj["Key"]),
                        }
                    )

            result = {
                "files": files,
                "count": len(files),
                "truncated": response.get("IsTruncated", False),
                "next_token": response.get("NextContinuationToken"),
                "prefix": prefix,
            }

            logger.info(f"Listed {len(files)} files from S3 with prefix: {prefix}")
            return result

        except ClientError as e:
            error_msg = f"Failed to list files from S3: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during listing: {str(e)}"
            logger.error(error_msg)
            raise S3StorageError(error_msg) from e

    def file_exists(self, key: str) -> bool:
        """
        Check if a file exists in S3 bucket.

        Args:
            key: S3 object key to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise S3StorageError(f"Error checking file existence: {str(e)}") from e

    def get_file_info(self, key: str) -> Dict[str, Any]:
        """
        Get detailed information about a file in S3.

        Args:
            key: S3 object key

        Returns:
            Dict containing file information

        Raises:
            S3StorageError: If file not found or access fails
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)

            return {
                "key": key,
                "size": response["ContentLength"],
                "content_type": response.get("ContentType", "unknown"),
                "last_modified": response["LastModified"].isoformat(),
                "etag": response["ETag"].strip('"'),
                "metadata": response.get("Metadata", {}),
                "url": self.get_file_url(key),
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                raise S3StorageError(f"File not found: {key}") from e
            else:
                raise S3StorageError(f"Error getting file info: {str(e)}") from e

    def get_file_url(self, key: str, public: bool = False, expires_in: int = 3600) -> str:
        """
        Generate URL for a file in S3.

        Args:
            key: S3 object key
            public: Whether to generate public URL
            expires_in: Expiration time for presigned URL (seconds)

        Returns:
            File URL
        """
        if public:
            # Generate public URL
            if getattr(self, "endpoint_url", None):
                base = self.endpoint_url.rstrip("/")
                return f"{base}/{self.bucket_name}/{key}"
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"
        else:
            # Generate presigned URL
            try:
                url = self.s3_client.generate_presigned_url(
                    "get_object", Params={"Bucket": self.bucket_name, "Key": key}, ExpiresIn=expires_in
                )
                return url
            except ClientError as e:
                raise S3StorageError(f"Error generating presigned URL: {str(e)}") from e

    def generate_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for accessing an S3 object.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            expires_in: Expiration time in seconds (default: 1 hour)

        Returns:
            Pre-signed URL string

        Raises:
            S3StorageError: If URL generation fails
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
            )
            logger.debug(f"Generated presigned URL for {bucket}/{key} (expires in {expires_in}s)")
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {bucket}/{key}: {e}")
            raise S3StorageError(f"Error generating presigned URL: {str(e)}") from e

    def generate_presigned_upload_url(
        self,
        key: str,
        expires_in: int = 3600,
        content_type: Optional[str] = None,
        file_size_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate presigned URL for direct client uploads.

        Args:
            key: S3 object key for the upload
            expires_in: URL expiration time in seconds
            content_type: Expected content type
            file_size_limit: Maximum file size in bytes

        Returns:
            Dict containing presigned URL and form fields
        """
        try:
            conditions = []

            if content_type:
                conditions.append({"Content-Type": content_type})

            if file_size_limit:
                conditions.append(["content-length-range", 1, file_size_limit])

            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name, Key=key, ExpiresIn=expires_in, Conditions=conditions
            )

            return {"url": response["url"], "fields": response["fields"], "expires_in": expires_in}

        except ClientError as e:
            raise S3StorageError(f"Error generating presigned upload URL: {str(e)}") from e

    # Marketplace-specific helper methods

    def upload_product_image(
        self, product_id: str, image_file: Union[InMemoryUploadedFile, TemporaryUploadedFile], image_type: str = "main"
    ) -> Dict[str, Any]:
        """
        Upload product image with marketplace-specific naming and settings.

        Args:
            product_id: Product UUID
            image_file: Image file to upload
            image_type: Type of image ('main', 'gallery', 'thumbnail')

        Returns:
            Upload result with product-specific metadata
        """
        # Generate product-specific key
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        file_extension = os.path.splitext(image_file.name)[1].lower()
        key = f"products/{product_id}/{image_type}_{timestamp}{file_extension}"

        # Add product-specific metadata
        metadata = {"product_id": product_id, "image_type": image_type, "uploaded_by": "marketplace"}

        return self.upload_file(
            file_obj=image_file, key=key, metadata=metadata, public=True  # Product images are public
        )

    def upload_user_avatar(
        self, user_id: str, avatar_file: Union[InMemoryUploadedFile, TemporaryUploadedFile]
    ) -> Dict[str, Any]:
        """
        Upload user avatar with user-specific naming.

        Args:
            user_id: User UUID
            avatar_file: Avatar image file

        Returns:
            Upload result
        """
        file_extension = os.path.splitext(avatar_file.name)[1].lower()
        key = f"avatars/{user_id}/avatar{file_extension}"

        metadata = {"user_id": user_id, "file_type": "avatar"}

        return self.upload_file(file_obj=avatar_file, key=key, metadata=metadata, public=True)

    def list_product_images(self, product_id: str) -> List[Dict[str, Any]]:
        """
        List all images for a specific product.

        Args:
            product_id: Product UUID

        Returns:
            List of product images
        """
        prefix = f"products/{product_id}/"
        result = self.list_files(prefix=prefix)
        return result["files"]

    def delete_product_images(self, product_id: str) -> int:
        """
        Delete all images for a specific product.

        Args:
            product_id: Product UUID

        Returns:
            Number of deleted files
        """
        images = self.list_product_images(product_id)
        deleted_count = 0

        for image in images:
            try:
                self.delete_file(image["key"])
                deleted_count += 1
            except S3StorageError as e:
                logger.error(f"Failed to delete image {image['key']}: {str(e)}")

        return deleted_count

    # Product-specific S3 operations

    def get_product_images(self, product_id: str) -> List[Dict[str, Any]]:
        """
        Get all images for a specific product with detailed information.

        Args:
            product_id: Product UUID

        Returns:
            List of product images with metadata
        """
        try:
            prefix = f"products/{product_id}/"
            result = self.list_files(prefix=prefix)

            # Enhance each image with additional metadata
            enhanced_images = []
            for image in result["files"]:
                # Extract image type from filename
                filename = image["key"].split("/")[-1]
                image_type = "main"
                if "gallery" in filename:
                    image_type = "gallery"
                elif "thumbnail" in filename:
                    image_type = "thumbnail"

                enhanced_image = {
                    **image,
                    "product_id": product_id,
                    "image_type": image_type,
                    "filename": filename,
                    "is_main": image_type == "main",
                    "public_url": self.get_file_url(image["key"], public=True),
                }
                enhanced_images.append(enhanced_image)

            # Sort images: main first, then gallery, then thumbnails
            type_priority = {"main": 0, "gallery": 1, "thumbnail": 2}
            enhanced_images.sort(key=lambda x: (type_priority.get(x["image_type"], 3), x["filename"]))

            logger.info(f"Retrieved {len(enhanced_images)} images for product {product_id}")
            return enhanced_images

        except S3StorageError as e:
            logger.error(f"Failed to get images for product {product_id}: {str(e)}")
            return []

    def delete_specific_product_image(self, product_id: str, image_key: str) -> bool:
        """
        Delete a specific product image by key.

        Args:
            product_id: Product UUID (for validation)
            image_key: Full S3 key of the image to delete

        Returns:
            True if successful

        Raises:
            S3StorageError: If deletion fails or image doesn't belong to product
        """
        # Validate that the image belongs to the specified product
        if not image_key.startswith(f"products/{product_id}/"):
            raise S3StorageError(f"Image {image_key} does not belong to product {product_id}")

        try:
            success = self.delete_file(image_key)
            if success:
                logger.info(f"Deleted product image: {image_key}")
            return success
        except S3StorageError as e:
            logger.error(f"Failed to delete product image {image_key}: {str(e)}")
            raise

    def get_product_main_image(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the main image for a product.

        Args:
            product_id: Product UUID

        Returns:
            Main image information or None if not found
        """
        images = self.get_product_images(product_id)

        # Look for main image first
        for image in images:
            if image["image_type"] == "main":
                return image

        # If no main image, return the first image
        return images[0] if images else None

    # Profile-specific S3 operations

    def upload_profile_picture(
        self,
        user_id: str,
        image_file: Union[InMemoryUploadedFile, TemporaryUploadedFile],
        replace_existing: bool = True,
    ) -> Dict[str, Any]:
        """
        Upload user profile picture.

        Args:
            user_id: User UUID
            image_file: Profile image file
            replace_existing: Whether to replace existing profile picture

        Returns:
            Upload result with profile-specific metadata
        """
        # Delete existing profile picture if requested
        if replace_existing:
            try:
                existing_images = self.list_profile_pictures(user_id)
                for image in existing_images:
                    self.delete_file(image["key"])
                logger.info(f"Deleted {len(existing_images)} existing profile pictures for user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to delete existing profile pictures for user {user_id}: {str(e)}")

        # Generate profile-specific key
        file_extension = os.path.splitext(image_file.name)[1].lower()
        if not file_extension:
            file_extension = ".jpg"  # Default extension

        key = f"profiles/{user_id}/profile{file_extension}"

        # Add profile-specific metadata
        metadata = {"user_id": user_id, "file_type": "profile_picture", "uploaded_at": timezone.now().isoformat()}

        return self.upload_file(
            file_obj=image_file, key=key, metadata=metadata, public=True  # Profile pictures are public
        )

    def get_profile_picture(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user's profile picture information.

        Args:
            user_id: User UUID

        Returns:
            Profile picture information or None if not found
        """
        try:
            prefix = f"profiles/{user_id}/"
            result = self.list_files(prefix=prefix, max_keys=10)

            if not result["files"]:
                return None

            # Get the most recent profile picture
            profile_pic = result["files"][0]  # Files are sorted by last_modified

            return {
                **profile_pic,
                "user_id": user_id,
                "file_type": "profile_picture",
                "public_url": self.get_file_url(profile_pic["key"], public=True),
                "filename": profile_pic["key"].split("/")[-1],
            }

        except S3StorageError as e:
            logger.error(f"Failed to get profile picture for user {user_id}: {str(e)}")
            return None

    def list_profile_pictures(self, user_id: str) -> List[Dict[str, Any]]:
        """
        List all profile pictures for a user (usually just one).

        Args:
            user_id: User UUID

        Returns:
            List of profile pictures
        """
        try:
            prefix = f"profiles/{user_id}/"
            result = self.list_files(prefix=prefix)

            # Enhance each image with profile-specific metadata
            enhanced_images = []
            for image in result["files"]:
                enhanced_image = {
                    **image,
                    "user_id": user_id,
                    "file_type": "profile_picture",
                    "public_url": self.get_file_url(image["key"], public=True),
                    "filename": image["key"].split("/")[-1],
                }
                enhanced_images.append(enhanced_image)

            return enhanced_images

        except S3StorageError as e:
            logger.error(f"Failed to list profile pictures for user {user_id}: {str(e)}")
            return []

    def delete_profile_picture(self, user_id: str) -> bool:
        """
        Delete user's profile picture.

        Args:
            user_id: User UUID

        Returns:
            True if successful
        """
        try:
            profile_pics = self.list_profile_pictures(user_id)
            deleted_count = 0

            for pic in profile_pics:
                try:
                    self.delete_file(pic["key"])
                    deleted_count += 1
                except S3StorageError as e:
                    logger.error(f"Failed to delete profile picture {pic['key']}: {str(e)}")

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} profile pictures for user {user_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete profile pictures for user {user_id}: {str(e)}")
            return False

    def update_profile_picture(
        self, user_id: str, image_file: Union[InMemoryUploadedFile, TemporaryUploadedFile]
    ) -> Dict[str, Any]:
        """
        Update user's profile picture (convenience method that replaces existing).

        Args:
            user_id: User UUID
            image_file: New profile image file

        Returns:
            Upload result
        """
        return self.upload_profile_picture(user_id=user_id, image_file=image_file, replace_existing=True)


# Convenience instance for easy import
s3_storage = S3Storage() if getattr(settings, "USE_S3", False) else None


def get_s3_storage() -> S3Storage:
    """Get S3Storage instance with configuration validation"""
    if not getattr(settings, "USE_S3", False):
        raise S3StorageError("S3 storage is not enabled")

    if s3_storage is None:
        return S3Storage()

    return s3_storage
