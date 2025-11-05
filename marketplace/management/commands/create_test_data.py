"""
Django management command to quickly create test data without downloading images
Usage: python manage.py create_test_data
"""

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from marketplace.models import Category, Product

User = get_user_model()


class Command(BaseCommand):
    help = "Create basic test data quickly (no image downloads)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before creating",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            Product.objects.all().delete()
            Category.objects.all().delete()

        self.stdout.write("Creating test data...")

        # Create categories
        categories = self.create_categories()

        # Get or create test users
        sellers = self.get_or_create_users()

        # Create products
        self.create_products(categories, sellers)

        self.stdout.write(
            self.style.SUCCESS(
                "Successfully created test data!\n"
                f"- {len(categories)} categories\n"
                f"- {len(sellers)} sellers\n"
                f"- {Product.objects.count()} products"
            )
        )

    def create_categories(self):
        """Create basic categories"""
        categories_data = [
            {"name": "Sofas", "description": "Comfortable seating solutions"},
            {"name": "Tables", "description": "Dining and coffee tables"},
            {"name": "Chairs", "description": "Seating for every room"},
            {"name": "Beds", "description": "Bedroom furniture"},
            {"name": "Storage", "description": "Organization solutions"},
            {"name": "Lighting", "description": "Lamps and fixtures"},
        ]

        categories = []
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data["name"],
                defaults={
                    "description": cat_data["description"],
                    "slug": slugify(cat_data["name"]),
                    "is_active": True,
                },
            )
            categories.append(category)
            if created:
                self.stdout.write(f"Created category: {category.name}")

        return categories

    def get_or_create_users(self):
        """Get existing users or create test users"""
        users = list(User.objects.all()[:5])  # Get up to 5 existing users

        if not users:
            # Create a test user if none exist
            user = User.objects.create_user(
                username="testuser", email="test@example.com", first_name="Test", last_name="User"
            )
            users = [user]
            self.stdout.write(f"Created test user: {user.username}")

        return users

    def create_products(self, categories, sellers):
        """Create sample products"""
        product_templates = [
            {
                "name": "Modern Sofa",
                "description": "A comfortable modern sofa perfect for any living room.",
                "price": Decimal("899.99"),
                "category": "Sofas",
                "colors": ["Gray", "Blue"],
                "materials": "Fabric, Wood",
                "tags": ["modern", "comfortable"],
                "stock_quantity": 10,
            },
            {
                "name": "Oak Dining Table",
                "description": "Beautiful solid oak dining table that seats 6 people.",
                "price": Decimal("1299.99"),
                "category": "Tables",
                "colors": ["Natural"],
                "materials": "Solid Oak",
                "tags": ["dining", "oak", "wood"],
                "stock_quantity": 5,
            },
            {
                "name": "Office Chair",
                "description": "Ergonomic office chair with lumbar support.",
                "price": Decimal("299.99"),
                "category": "Chairs",
                "colors": ["Black", "Gray"],
                "materials": "Mesh, Plastic",
                "tags": ["office", "ergonomic"],
                "stock_quantity": 15,
            },
            {
                "name": "Queen Bed Frame",
                "description": "Sturdy queen size bed frame with modern design.",
                "price": Decimal("599.99"),
                "category": "Beds",
                "colors": ["White", "Black"],
                "materials": "Metal, Wood",
                "tags": ["bed", "queen", "modern"],
                "stock_quantity": 8,
            },
            {
                "name": "Bookshelf",
                "description": "Five-tier bookshelf for storage and display.",
                "price": Decimal("199.99"),
                "category": "Storage",
                "colors": ["Brown", "White"],
                "materials": "Wood",
                "tags": ["books", "storage", "display"],
                "stock_quantity": 12,
            },
            {
                "name": "Floor Lamp",
                "description": "Modern floor lamp with adjustable brightness.",
                "price": Decimal("149.99"),
                "category": "Lighting",
                "colors": ["Black", "White"],
                "materials": "Metal, Fabric",
                "tags": ["lamp", "modern", "lighting"],
                "stock_quantity": 20,
            },
        ]

        # Create multiple variations of each product
        for i in range(20):  # Create 20 products
            template = product_templates[i % len(product_templates)]

            # Find the category
            category = None
            for cat in categories:
                if cat.name == template["category"]:
                    category = cat
                    break

            if not category:
                category = categories[0]

            # Create product name variation
            variation_num = (i // len(product_templates)) + 1
            product_name = f"{template['name']}"
            if variation_num > 1:
                product_name += f" - Style {variation_num}"

            # Random seller
            seller = random.choice(sellers)

            # Random price variation
            base_price = template["price"]
            price_variation = random.uniform(0.8, 1.2)  # ±20% price variation
            final_price = base_price * Decimal(str(price_variation))

            product, created = Product.objects.get_or_create(
                name=product_name,
                seller=seller,
                defaults={
                    "description": template["description"],
                    "short_description": template["description"][:100],
                    "category": category,
                    "price": final_price.quantize(Decimal("0.01")),
                    "stock_quantity": template["stock_quantity"] + random.randint(-3, 5),
                    "condition": random.choice(["new", "like_new", "good"]),
                    "brand": f"Brand{random.randint(1, 5)}",
                    "colors": template["colors"],
                    "materials": template["materials"],
                    "tags": template["tags"],
                    "is_featured": random.choice([True, False, False, False]),  # 25% chance
                    "is_active": True,
                    "weight": Decimal(str(random.uniform(1, 50))),
                    "dimensions_length": Decimal(str(random.randint(50, 200))),
                    "dimensions_width": Decimal(str(random.randint(30, 150))),
                    "dimensions_height": Decimal(str(random.randint(20, 100))),
                },
            )

            if created:
                self.stdout.write(f"Created product: {product.name}")
