# myapp/management/commands/test_s3.py
# Replace 'myapp' with your actual Django app name where you place this file.
# Run this command with: python manage.py test_s3
# This script tests basic S3 operations: upload, check existence, download, and delete.
# It uses a temporary in-memory file for testing to avoid affecting real files.

from io import BytesIO

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Tests basic AWS S3 operations using Django storage backend"

    def handle(self, *args, **options):
        if not getattr(settings, "USE_S3", False):
            self.stdout.write(self.style.ERROR("S3 is not enabled in settings. Set USE_S3=True to test."))
            return

        storage = default_storage  # Or get_storage_class()() if you want static storage, etc.

        # Test file details
        test_content = b"This is a test file for S3 operations."
        test_file_name = "test_s3_file.txt"
        test_path = f"test/{test_file_name}"  # Use a 'test/' prefix to isolate

        self.stdout.write(self.style.NOTICE("Starting S3 tests..."))

        try:
            # 1. Upload a file
            self.stdout.write("Uploading file...")
            file_obj = BytesIO(test_content)
            storage.save(test_path, file_obj)
            self.stdout.write(self.style.SUCCESS(f"File uploaded to: {test_path}"))

            # 2. Check if file exists
            if storage.exists(test_path):
                self.stdout.write(self.style.SUCCESS("File exists check: PASSED"))
            else:
                raise Exception("File exists check: FAILED")

            # 3. Download the file
            self.stdout.write("Downloading file...")
            downloaded_content = storage.open(test_path).read()
            if downloaded_content == test_content:
                self.stdout.write(self.style.SUCCESS("File download and content match: PASSED"))
            else:
                raise Exception("File download content mismatch: FAILED")

            # 4. Get file URL
            file_url = storage.url(test_path)
            self.stdout.write(self.style.SUCCESS(f"File URL: {file_url}"))

            # 5. Delete the file
            self.stdout.write("Deleting file...")
            storage.delete(test_path)
            if not storage.exists(test_path):
                self.stdout.write(self.style.SUCCESS("File delete: PASSED"))
            else:
                raise Exception("File delete: FAILED")

            self.stdout.write(self.style.SUCCESS("All S3 tests passed successfully!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during S3 test: {str(e)}"))
            raise
