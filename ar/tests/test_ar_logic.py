import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ar.models import ProductARModel
from ar.services.ar_service import ARService
from marketplace.models import Category, Product
from marketplace.serializers import ProductDetailSerializer

User = get_user_model()


class ARLogicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test_ar_user", email="ar_user@example.com", password="password", id=uuid.uuid4()
        )
        self.category = Category.objects.create(name="AR Test Cat", slug="ar-test")

        # Product with AR Model
        self.p_with_ar = Product.objects.create(
            name="AR Product",
            description="Desc",
            price=Decimal("100.00"),
            seller=self.user,
            category=self.category,
            is_active=True,
        )

        self.ar_model = ProductARModel.objects.create(
            product=self.p_with_ar,
            s3_key="models/ar_product.glb",
            s3_bucket="test-bucket",
            original_filename="ar_product.glb",
            file_size=1024,
            content_type="model/gltf-binary",
        )

        # Product without AR Model
        self.p_without_ar = Product.objects.create(
            name="No AR Product",
            description="Desc",
            price=Decimal("50.00"),
            seller=self.user,
            category=self.category,
            is_active=True,
        )

        self.service = ARService()

    def test_ar_service_logic(self):
        """Test service logic directly"""
        self.assertTrue(self.service.has_3d_model(str(self.p_with_ar.id)).value)
        self.assertFalse(self.service.has_3d_model(str(self.p_without_ar.id)).value)

        url_res = self.service.get_ar_view_url(str(self.p_with_ar.id))
        self.assertTrue(url_res.ok)
        self.assertIn("/api/system/s3-models/models/ar_product.glb", url_res.value)

        url_res_none = self.service.get_ar_view_url(str(self.p_without_ar.id))
        self.assertTrue(url_res_none.ok)
        self.assertIsNone(url_res_none.value)

    def test_serializers_use_service(self):
        """Test that serializers use AR service"""
        serializer = ProductDetailSerializer(self.p_with_ar)
        self.assertTrue(serializer.data["has_ar_model"])

        serializer = ProductDetailSerializer(self.p_without_ar)
        self.assertFalse(serializer.data["has_ar_model"])
