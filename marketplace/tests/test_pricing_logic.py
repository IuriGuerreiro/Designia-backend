import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from marketplace.models import Category, Product
from marketplace.serializers import ProductDetailSerializer, ProductListSerializer
from marketplace.services.pricing_service import PricingService

User = get_user_model()


class PricingLogicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test_pricer", email="pricer@example.com", password="password", id=uuid.uuid4()
        )
        self.category = Category.objects.create(name="Pricing Test Cat", slug="pricing-test")

        # Product on sale
        self.p_sale = Product.objects.create(
            name="Sale Product",
            description="Desc",
            price=Decimal("80.00"),
            original_price=Decimal("100.00"),
            seller=self.user,
            category=self.category,
            is_active=True,
        )

        # Product NOT on sale
        self.p_regular = Product.objects.create(
            name="Regular Product",
            description="Desc",
            price=Decimal("100.00"),
            original_price=None,
            seller=self.user,
            category=self.category,
            is_active=True,
        )

        self.pricing_service = PricingService()

    def test_pricing_service_calculations(self):
        """Test the service logic directly"""
        # Sale Product
        self.assertTrue(self.pricing_service.is_on_sale(self.p_sale).value)
        discount = self.pricing_service.calculate_discount_percentage(self.p_sale).value
        self.assertEqual(discount, Decimal("20.00"))

        # Regular Product
        self.assertFalse(self.pricing_service.is_on_sale(self.p_regular).value)
        discount = self.pricing_service.calculate_discount_percentage(self.p_regular).value
        self.assertEqual(discount, Decimal("0"))

    def test_serializers_use_service(self):
        """Test that serializers calculate pricing correctly"""
        # List Serializer
        serializer = ProductListSerializer(self.p_sale)
        data = serializer.data
        self.assertTrue(data["is_on_sale"])
        self.assertEqual(data["discount_percentage"], 20)

        serializer = ProductListSerializer(self.p_regular)
        data = serializer.data
        self.assertFalse(data["is_on_sale"])
        self.assertEqual(data["discount_percentage"], 0)

        # Detail Serializer
        serializer = ProductDetailSerializer(self.p_sale)
        data = serializer.data
        self.assertTrue(data["is_on_sale"])
        self.assertEqual(data["discount_percentage"], 20)
