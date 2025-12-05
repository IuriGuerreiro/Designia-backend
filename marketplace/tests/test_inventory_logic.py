import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from marketplace.models import Category, Product
from marketplace.serializers import ProductDetailSerializer, ProductListSerializer
from marketplace.services.inventory_service import InventoryService

User = get_user_model()


class InventoryLogicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test_inventory", email="inventory@example.com", password="password", id=uuid.uuid4()
        )
        self.category = Category.objects.create(name="Inventory Test Cat", slug="inventory-test")

        # In stock product
        self.p_stock = Product.objects.create(
            name="In Stock Product",
            description="Desc",
            price=Decimal("10.00"),
            stock_quantity=5,
            seller=self.user,
            category=self.category,
            is_active=True,
        )

        # Out of stock product
        self.p_out = Product.objects.create(
            name="Out of Stock Product",
            description="Desc",
            price=Decimal("10.00"),
            stock_quantity=0,
            seller=self.user,
            category=self.category,
            is_active=True,
        )

        self.service = InventoryService()

    def test_inventory_service_logic(self):
        """Test service logic directly"""
        self.assertTrue(self.service.is_in_stock(str(self.p_stock.id)).value)
        self.assertFalse(self.service.is_in_stock(str(self.p_out.id)).value)

        # Check availability
        self.assertTrue(self.service.check_availability(str(self.p_stock.id), 5).value)
        self.assertFalse(self.service.check_availability(str(self.p_stock.id), 6).value)

    def test_serializers_use_service(self):
        """Test that serializers retrieve inventory status via service"""
        # List Serializer
        serializer = ProductListSerializer(self.p_stock)
        self.assertTrue(serializer.data["is_in_stock"])

        serializer = ProductListSerializer(self.p_out)
        self.assertFalse(serializer.data["is_in_stock"])

        # Detail Serializer
        serializer = ProductDetailSerializer(self.p_stock)
        self.assertTrue(serializer.data["is_in_stock"])

        serializer = ProductDetailSerializer(self.p_out)
        self.assertFalse(serializer.data["is_in_stock"])

    def test_atomicity_reservation(self):
        """Test stock reservation logic"""
        # Reserve 2 items
        result = self.service.reserve_stock(str(self.p_stock.id), 2)
        self.assertTrue(result.ok)

        self.p_stock.refresh_from_db()
        self.assertEqual(self.p_stock.stock_quantity, 3)  # 5 - 2

        # Release 1 item
        result = self.service.release_stock(str(self.p_stock.id), 1)
        self.assertTrue(result.ok)

        self.p_stock.refresh_from_db()
        self.assertEqual(self.p_stock.stock_quantity, 4)  # 3 + 1
