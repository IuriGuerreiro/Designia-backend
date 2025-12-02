"""
Storage Abstraction Layer
==========================

Provides a unified interface for file storage operations (MinIO/S3).
"""

from .factory import StorageFactory
from .interface import StorageException, StorageFile, StorageInterface
from .s3_adapter import S3StorageAdapter

__all__ = [
    "StorageInterface",
    "StorageFile",
    "StorageException",
    "S3StorageAdapter",
    "StorageFactory",
]
