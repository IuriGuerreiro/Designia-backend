"""
Abstract Storage Provider interface following Dependency Inversion Principle.

This interface decouples business logic from storage infrastructure,
making code testable and allowing different storage backend implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from django.core.files.uploadedfile import UploadedFile


class StorageProvider(ABC):
    """Abstract storage provider interface for file operations."""

    @abstractmethod
    def upload_file(self, file: UploadedFile, path: str, **kwargs) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Upload file to storage.

        Args:
            file: Django UploadedFile instance
            path: Target path/key in storage
            **kwargs: Additional upload options (e.g., public=True, metadata={})

        Returns:
            (success: bool, file_key_or_error: str, upload_info: Optional[Dict])
            - If success=True, file_key_or_error is the storage key
            - If success=False, file_key_or_error is the error message
        """
        pass

    @abstractmethod
    def get_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """
        Get temporary signed URL for file access.

        Args:
            file_path: Storage path/key of the file
            expires_in: URL expiration time in seconds (default: 3600 = 1 hour)

        Returns:
            Signed URL string or None if file doesn't exist
        """
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Delete file from storage.

        Args:
            file_path: Storage path/key of the file

        Returns:
            (success: bool, message: str)
        """
        pass

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists in storage.

        Args:
            file_path: Storage path/key of the file

        Returns:
            True if file exists, False otherwise
        """
        pass
