"""
Local Storage Provider for testing and development.

Stores files in memory for tests or on local filesystem for development.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from django.core.files.uploadedfile import UploadedFile

from .storage_interface import StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    """
    Mock/local storage provider for testing.

    Stores file metadata in memory for test assertions.
    Does not actually save files to disk.
    """

    def __init__(self):
        """Initialize local storage provider with empty storage."""
        # In-memory storage of file metadata
        self.files: Dict[str, Dict[str, Any]] = {}
        self.upload_attempts: List[Dict[str, Any]] = []

    def upload_file(self, file: UploadedFile, path: str, **kwargs) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Mock upload file (stores metadata only).

        Args:
            file: Django UploadedFile instance
            path: Target path
            **kwargs: Additional options

        Returns:
            (success, file_path, upload_info)
        """
        try:
            # Store file metadata
            file_info = {
                "name": file.name,
                "size": file.size,
                "content_type": file.content_type,
                "path": path,
                "kwargs": kwargs,
            }

            self.files[path] = file_info
            self.upload_attempts.append(file_info)

            logger.info(f"Local storage: Uploaded {file.name} to {path}")

            upload_result = {
                "success": True,
                "key": path,
                "size": file.size,
                "content_type": file.content_type,
            }

            return True, path, upload_result

        except Exception as e:
            logger.error(f"Local storage upload failed: {e}")
            return False, str(e), None

    def get_file_url(self, file_path: str, expires_in: int = 3600) -> Optional[str]:
        """
        Get mock file URL.

        Args:
            file_path: Storage path
            expires_in: Expiration time (ignored in mock)

        Returns:
            Mock URL or None if file doesn't exist
        """
        if file_path in self.files:
            # Return a mock URL
            return f"http://localhost:8000/media/{file_path}?expires={expires_in}"
        return None

    def delete_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Delete file from local storage.

        Args:
            file_path: Storage path

        Returns:
            (success, message)
        """
        if file_path in self.files:
            del self.files[file_path]
            logger.info(f"Local storage: Deleted {file_path}")
            return True, "File deleted successfully"
        else:
            return False, "File not found"

    def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists in local storage.

        Args:
            file_path: Storage path

        Returns:
            True if file exists, False otherwise
        """
        return file_path in self.files

    # Test helper methods
    def reset(self):
        """Clear all stored files."""
        self.files.clear()
        self.upload_attempts.clear()

    def get_file_info(self, path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata for testing."""
        return self.files.get(path)

    def get_all_files(self) -> Dict[str, Dict[str, Any]]:
        """Get all stored files metadata."""
        return self.files.copy()
