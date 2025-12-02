"""
Storage Factory
===============

Factory pattern for creating S3/MinIO storage instances.
Implements the Dependency Inversion Principle.
"""

import logging

from .interface import StorageInterface
from .s3_adapter import S3StorageAdapter

logger = logging.getLogger(__name__)


class StorageFactory:
    """
    Factory for creating S3/MinIO storage backend.

    Usage:
        # In your code
        storage = StorageFactory.create()
    """

    @staticmethod
    def create() -> StorageInterface:
        """
        Create an S3 storage backend instance.

        Returns:
            S3StorageAdapter instance configured from settings
        """
        logger.info("Creating S3/MinIO storage backend")
        return S3StorageAdapter()

    @staticmethod
    def create_s3() -> S3StorageAdapter:
        """
        Create S3/MinIO storage backend explicitly.

        Returns:
            S3StorageAdapter instance
        """
        return S3StorageAdapter()
