"""
Storage Infrastructure Tests
=============================

Unit tests for S3/MinIO storage abstraction layer.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from infrastructure.storage import S3StorageAdapter, StorageException, StorageFactory, StorageFile, StorageInterface


class StorageInterfaceTest(TestCase):
    """Test StorageInterface contract."""

    def test_interface_is_abstract(self):
        """StorageInterface should not be instantiable."""
        with self.assertRaises(TypeError):
            StorageInterface()


@override_settings(
    AWS_STORAGE_BUCKET_NAME="test-bucket",
    AWS_ACCESS_KEY_ID="test-key",
    AWS_SECRET_ACCESS_KEY="test-secret",
)
class S3StorageAdapterTest(TestCase):
    """Test S3StorageAdapter implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_content = b"S3 test content"

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_upload_file_success(self, mock_storage_class):
        """Test successful file upload to S3."""
        # Mock the storage instance
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage

        mock_storage.save.return_value = "test/s3upload.txt"
        mock_storage.size.return_value = len(self.test_content)
        mock_storage.url.return_value = "https://s3.amazonaws.com/bucket/test/s3upload.txt"

        # Create adapter and upload
        adapter = S3StorageAdapter()
        result = adapter.upload(
            file=BytesIO(self.test_content),
            path="test/s3upload.txt",
            content_type="image/jpeg",
        )

        self.assertIsInstance(result, StorageFile)
        self.assertEqual(result.key, "test/s3upload.txt")
        self.assertIn("s3.amazonaws.com", result.url)
        self.assertEqual(result.size, len(self.test_content))
        self.assertEqual(result.bucket, "test-bucket")

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_delete_file_success(self, mock_storage_class):
        """Test successful S3 file deletion."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.exists.return_value = True

        adapter = S3StorageAdapter()
        result = adapter.delete("test/file.txt")

        self.assertTrue(result)
        mock_storage.delete.assert_called_once_with("test/file.txt")

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_delete_nonexistent_file(self, mock_storage_class):
        """Test deleting a file that doesn't exist."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.exists.return_value = False

        adapter = S3StorageAdapter()
        result = adapter.delete("nonexistent/file.txt")

        self.assertFalse(result)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_exists(self, mock_storage_class):
        """Test S3 file existence check."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.exists.return_value = True

        adapter = S3StorageAdapter()
        exists = adapter.exists("test/file.txt")

        self.assertTrue(exists)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_get_url(self, mock_storage_class):
        """Test URL generation for S3 files."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.url.return_value = "https://s3.amazonaws.com/bucket/test/file.txt"

        adapter = S3StorageAdapter()
        url = adapter.get_url("test/file.txt")

        self.assertIn("s3.amazonaws.com", url)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_get_size(self, mock_storage_class):
        """Test file size retrieval."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.exists.return_value = True
        mock_storage.size.return_value = 1024

        adapter = S3StorageAdapter()
        size = adapter.get_size("test/file.txt")

        self.assertEqual(size, 1024)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_get_size_nonexistent_file(self, mock_storage_class):
        """Test size retrieval for nonexistent file raises exception."""
        mock_storage = MagicMock()
        mock_storage_class.return_value = mock_storage
        mock_storage.exists.return_value = False

        adapter = S3StorageAdapter()

        with self.assertRaises(StorageException):
            adapter.get_size("nonexistent/file.txt")

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_bucket_name(self, mock_storage_class):
        """Test bucket name property."""
        mock_storage_class.return_value = MagicMock()

        adapter = S3StorageAdapter()
        self.assertEqual(adapter.bucket_name, "test-bucket")


class StorageFactoryTest(TestCase):
    """Test StorageFactory."""

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_create_storage(self, mock_storage):
        """Test factory creates S3 storage."""
        mock_storage.return_value = MagicMock()
        storage = StorageFactory.create()
        self.assertIsInstance(storage, S3StorageAdapter)

    @patch("infrastructure.storage.s3_adapter.S3Boto3Storage")
    def test_create_s3_explicit(self, mock_storage):
        """Test explicit S3 creation."""
        mock_storage.return_value = MagicMock()
        storage = StorageFactory.create_s3()
        self.assertIsInstance(storage, S3StorageAdapter)
