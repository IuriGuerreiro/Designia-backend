from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ar.models import ProductARModelDownload
from marketplace.tests.factories import CategoryFactory, ProductARModelFactory, ProductFactory, UserFactory


@override_settings(FEATURE_FLAGS={})
class ProductARViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.seller = UserFactory()
        self.category = CategoryFactory()

        # Product with AR Model
        self.product_with_ar = ProductFactory(seller=self.seller, category=self.category)
        self.ar_model = ProductARModelFactory(product=self.product_with_ar, uploaded_by=self.seller)

        # Product without AR Model
        self.product_without_ar = ProductFactory(seller=self.seller, category=self.category)

        self.product_with_ar_url = reverse("marketplace:product-detail", kwargs={"slug": self.product_with_ar.slug})
        self.product_without_ar_url = reverse(
            "marketplace:product-detail", kwargs={"slug": self.product_without_ar.slug}
        )

    def test_product_detail_has_ar_model_field(self):
        response = self.client.get(self.product_with_ar_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_ar_model"])

        response = self.client.get(self.product_without_ar_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["has_ar_model"])


@override_settings(
    USE_S3=True, AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test", AWS_STORAGE_BUCKET_NAME="test-bucket"
)
class ARModelViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.seller = UserFactory(username="ar_seller", role="seller")
        self.other_user = UserFactory(username="other_user")
        self.admin = UserFactory(username="admin", role="admin", is_staff=True)
        self.product = ProductFactory(seller=self.seller)
        self.ar_model = ProductARModelFactory(product=self.product, uploaded_by=self.seller)

    @patch("ar.views.get_s3_storage")
    def test_create_ar_model_success(self, mock_get_storage):
        """Test uploading a new AR model."""
        mock_storage = MagicMock()
        mock_storage.bucket_name = "test-bucket"
        mock_storage.upload_product_3d_model.return_value = {
            "key": f"ar/{self.product.id}/model.glb",
            "bucket": "test-bucket",
            "size": 1024,
            "content_type": "model/gltf-binary",
        }
        mock_get_storage.return_value = mock_storage

        self.client.force_authenticate(user=self.seller)
        file = SimpleUploadedFile("model.glb", b"dummy content", content_type="model/gltf-binary")

        data = {"product_id": str(self.product.id), "model_file": file}

        response = self.client.post(reverse("ar:ar-model-list"), data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["product_id"], str(self.product.id))
        mock_storage.upload_product_3d_model.assert_called_once()

    def test_create_ar_model_permission_denied(self):
        """Test user cannot upload AR model for another seller's product."""
        self.client.force_authenticate(user=self.other_user)
        file = SimpleUploadedFile("model.glb", b"dummy content", content_type="model/gltf-binary")

        data = {"product_id": str(self.product.id), "model_file": file}

        response = self.client.post(reverse("ar:ar-model-list"), data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_ar_model(self):
        """Test retrieving AR model metadata."""
        # Retrieve using product ID as lookup_field="pk"
        url = reverse("ar:ar-model-detail", kwargs={"pk": self.product.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.ar_model.id)

    @patch("ar.views.get_s3_storage")
    def test_download_link(self, mock_get_storage):
        """Test generating a download link."""
        mock_storage = MagicMock()
        mock_storage.download_product_3d_model.return_value = "https://s3.example.com/signed-url"
        mock_get_storage.return_value = mock_storage

        self.client.force_authenticate(user=self.other_user)
        url = reverse("ar:ar-model-download-link", kwargs={"pk": self.product.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["download_url"], "https://s3.example.com/signed-url")
        mock_storage.download_product_3d_model.assert_called_once()

        # Verify last_download_requested_at updated
        self.ar_model.refresh_from_db()
        self.assertIsNotNone(self.ar_model.last_download_requested_at)

    def test_catalog_permission(self):
        """Test only admin can access catalog."""
        self.client.force_authenticate(user=self.seller)
        response = self.client.get(reverse("ar:ar-model-catalog"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("ar:ar-model-catalog"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ARModelDownloadViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.product = ProductFactory()
        self.ar_model = ProductARModelFactory(product=self.product)

    def test_create_download_record(self):
        """Test recording a download."""
        self.client.force_authenticate(user=self.user)
        data = {"product_id": str(self.product.id), "platform": "web_viewer"}
        response = self.client.post(reverse("ar:ar-model-download-list"), data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ProductARModelDownload.objects.filter(user=self.user, product_model=self.ar_model).exists())

    def test_list_own_downloads(self):
        """Test user can list their own downloads."""
        ProductARModelDownload.objects.create(user=self.user, product_model=self.ar_model, platform="app")

        other_user = UserFactory()
        ProductARModelDownload.objects.create(user=other_user, product_model=self.ar_model, platform="app")

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("ar:ar-model-download-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assuming default pagination is not set in test settings, or it returns a list if not configured
        results = response.data if isinstance(response.data, list) else response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["product_model_id"], self.ar_model.id)
