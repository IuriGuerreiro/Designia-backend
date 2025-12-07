from unittest.mock import MagicMock, PropertyMock, patch

from django.test import RequestFactory, TestCase

from marketplace.tests.factories import ProductFactory, ProductImageFactory
from payment_system.views import get_product_image_url


class ViewsHelpersTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.product = ProductFactory()

    def test_get_product_image_url_no_images(self):
        url = get_product_image_url(self.product)
        self.assertEqual(url, "")

    def test_get_product_image_url_primary_image(self):
        ProductImageFactory(product=self.product, is_primary=True, image="products/test.jpg")
        # Mock get_presigned_url
        with patch(
            "marketplace.models.ProductImage.get_presigned_url", return_value="http://s3.com/presigned", create=True
        ):
            url = get_product_image_url(self.product)
            self.assertEqual(url, "http://s3.com/presigned")

    def test_get_product_image_url_fallback_to_image_url(self):
        ProductImageFactory(product=self.product, is_primary=True)
        # Mock get_presigned_url returning None
        with patch("marketplace.models.ProductImage.get_presigned_url", return_value=None, create=True):
            # Mock image_url property
            with patch(
                "marketplace.models.ProductImage.image_url", new_callable=PropertyMock, create=True
            ) as mock_prop:
                mock_prop.return_value = "http://cdn.com/image.jpg"

                url = get_product_image_url(self.product)
                self.assertEqual(url, "http://cdn.com/image.jpg")

    def test_get_product_image_url_fallback_to_basic_url(self):
        image = ProductImageFactory(product=self.product, is_primary=True, image="products/test.jpg")
        with patch("marketplace.models.ProductImage.get_presigned_url", return_value=None, create=True):
            # Mock image_url to raise error or return None
            with patch(
                "marketplace.models.ProductImage.image_url", new_callable=PropertyMock, create=True
            ) as mock_image_url:  # Assuming it returns None or raises
                # The code handles exceptions.

                # Note: request is needed for absolute URI if url is relative
                request = self.factory.get("/")
                # Django's image.url will be relative /media/products/test.jpg usually (or full if S3)
                # We can mock the image field
                image.image.storage.url = MagicMock(return_value="/media/products/test.jpg")

                # Configure property mock to raise exception
                mock_image_url.side_effect = Exception("No image_url")

                url = get_product_image_url(self.product, request)
                self.assertTrue(url.startswith("http://testserver/media/products/test.jpg"))
