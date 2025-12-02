"""
S3 Storage Adapter
==================

Concrete implementation of StorageInterface using AWS S3 via django-storages.
Implements the Dependency Inversion Principle by depending on the abstract StorageInterface.
"""

import logging
from typing import BinaryIO

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

from .interface import StorageException, StorageFile, StorageInterface

logger = logging.getLogger(__name__)


class S3StorageAdapter(StorageInterface):
    """
    AWS S3 storage implementation using django-storages.

    Configuration (in settings.py):
        AWS_ACCESS_KEY_ID: AWS access key
        AWS_SECRET_ACCESS_KEY: AWS secret key
        AWS_STORAGE_BUCKET_NAME: S3 bucket name
        AWS_S3_REGION_NAME: AWS region
        AWS_S3_CUSTOM_DOMAIN: Custom CDN domain (optional)
    """

    def __init__(self):
        """Initialize S3 storage backend."""
        self.storage = S3Boto3Storage()
        self._bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "default-bucket")

    def upload(
        self,
        file: BinaryIO,
        path: str,
        content_type: str,
        make_public: bool = True,
    ) -> StorageFile:
        """
        Upload a file to S3.

        Args:
            file: Binary file object to upload
            path: S3 key (destination path)
            content_type: MIME type
            make_public: If True, set ACL to public-read

        Returns:
            StorageFile with S3 metadata

        Raises:
            StorageException: If upload fails
        """
        try:
            # Save file using django-storages
            saved_path = self.storage.save(path, file)

            # Get file size
            size = self.storage.size(saved_path)

            # Get URL (public or signed based on settings)
            url = self.storage.url(saved_path)

            logger.info(f"Successfully uploaded file to S3: {saved_path}")

            return StorageFile(
                key=saved_path,
                url=url,
                size=size,
                content_type=content_type,
                bucket=self._bucket_name,
            )

        except Exception as e:
            logger.error(f"Failed to upload file to S3: {path}. Error: {str(e)}")
            raise StorageException(f"S3 upload failed: {str(e)}") from e

    def delete(self, key: str) -> bool:
        """
        Delete a file from S3.

        Args:
            key: S3 key to delete

        Returns:
            True if deletion successful

        Raises:
            StorageException: If deletion fails
        """
        try:
            if self.exists(key):
                self.storage.delete(key)
                logger.info(f"Successfully deleted file from S3: {key}")
                return True
            else:
                logger.warning(f"File not found in S3, cannot delete: {key}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete file from S3: {key}. Error: {str(e)}")
            raise StorageException(f"S3 deletion failed: {str(e)}") from e

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Get a URL to access the S3 object.

        Args:
            key: S3 key
            expires_in: Expiration time in seconds for signed URLs

        Returns:
            URL string (public or signed based on bucket configuration)

        Raises:
            StorageException: If URL generation fails
        """
        try:
            # django-storages handles signed URLs automatically
            # if AWS_QUERYSTRING_AUTH is True in settings
            url = self.storage.url(key)
            return url

        except Exception as e:
            logger.error(f"Failed to generate URL for S3 key: {key}. Error: {str(e)}")
            raise StorageException(f"URL generation failed: {str(e)}") from e

    def exists(self, key: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            key: S3 key to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            return self.storage.exists(key)
        except Exception as e:
            logger.error(f"Error checking existence of S3 key: {key}. Error: {str(e)}")
            return False

    def get_size(self, key: str) -> int:
        """
        Get file size from S3.

        Args:
            key: S3 key

        Returns:
            File size in bytes

        Raises:
            StorageException: If file doesn't exist or size retrieval fails
        """
        try:
            if not self.exists(key):
                raise StorageException(f"File not found: {key}")

            size = self.storage.size(key)
            return size

        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to get size for S3 key: {key}. Error: {str(e)}")
            raise StorageException(f"Size retrieval failed: {str(e)}") from e

    @property
    def bucket_name(self) -> str:
        """
        Get the S3 bucket name.

        Returns:
            Bucket name from settings
        """
        return self._bucket_name
