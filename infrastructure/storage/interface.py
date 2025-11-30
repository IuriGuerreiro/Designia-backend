"""
Storage Interface
=================

Abstract base class defining the contract for file storage operations.
Implements the Interface Segregation Principle by providing only essential storage methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Optional


@dataclass
class StorageFile:
    """
    Represents a stored file with its metadata.

    Attributes:
        key: Unique identifier/path for the file
        url: Public or signed URL to access the file
        size: File size in bytes
        content_type: MIME type of the file
        bucket: Storage bucket/container name (optional)
    """

    key: str
    url: str
    size: int
    content_type: str
    bucket: Optional[str] = None


class StorageInterface(ABC):
    """
    Abstract interface for file storage operations.

    Concrete implementations must provide:
        - S3StorageAdapter: AWS S3 storage
        - LocalStorageAdapter: Local filesystem storage
        - MockStorageAdapter: In-memory storage for testing
    """

    @abstractmethod
    def upload(
        self,
        file: BinaryIO,
        path: str,
        content_type: str,
        make_public: bool = True,
    ) -> StorageFile:
        """
        Upload a file to storage.

        Args:
            file: Binary file object to upload
            path: Destination path/key in storage
            content_type: MIME type of the file
            make_public: Whether to make the file publicly accessible

        Returns:
            StorageFile object with metadata

        Raises:
            StorageException: If upload fails
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a file from storage.

        Args:
            key: File identifier/path to delete

        Returns:
            True if deletion was successful, False otherwise

        Raises:
            StorageException: If deletion fails critically
        """
        pass

    @abstractmethod
    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Get a URL to access the file.

        Args:
            key: File identifier/path
            expires_in: URL expiration time in seconds (for signed URLs)

        Returns:
            URL string to access the file

        Raises:
            StorageException: If file doesn't exist or URL generation fails
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            key: File identifier/path to check

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    def get_size(self, key: str) -> int:
        """
        Get the size of a file in bytes.

        Args:
            key: File identifier/path

        Returns:
            File size in bytes

        Raises:
            StorageException: If file doesn't exist
        """
        pass

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        """
        Get the storage bucket/container name.

        Returns:
            Bucket name string
        """
        pass


class StorageException(Exception):
    """Base exception for storage operations."""

    pass
