import json
import logging
import os
import random
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from marketplace.models import Category, Product, ProductImage


logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Import scraped IKEA data from JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", type=str, default="tools/dataminer/output/ikea_data.json", help="Path to the JSON data file"
        )
        parser.add_argument(
            "--seller",
            type=str,
            help="Username of the seller to assign products to (defaults to first admin/superuser)",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        seller_username = options["seller"]

        # 1. Resolve File Path
        if not os.path.isabs(file_path):
            # Assume relative to project root (Designia-backend/)
            # But the command runs from manage.py, so relative path usually works if correct
            # Let's try to find it intelligently if default fails
            if not os.path.exists(file_path):
                # Try relative to the management command file location? No, keep simple.
                # Try checking if 'Designia-backend' is in the path
                alt_path = os.path.join(settings.BASE_DIR, file_path)
                if os.path.exists(alt_path):
                    file_path = alt_path
                else:
                    self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
                    return

        # 2. Get Seller
        seller = None
        if seller_username:
            try:
                seller = User.objects.get(username=seller_username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Seller user '{seller_username}' not found."))
                return
        else:
            # Default to first superuser
            seller = User.objects.filter(is_superuser=True).first()
            if not seller:
                self.stdout.write(
                    self.style.ERROR(
                        "No superuser found to assign products to. Please create one or specify --seller."
                    )
                )
                return

        self.stdout.write(self.style.SUCCESS(f"Importing data for seller: {seller.username}"))

        # 3. Load JSON
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading JSON: {e}"))
            return

        self.stdout.write(f"Found {len(data)} items to import.")

        # 4. Import Loop
        success_count = 0
        skipped_count = 0

        # Cache categories to avoid DB hits
        category_cache = {}

        with transaction.atomic():
            for item in data:
                try:
                    name = item.get("name")
                    if not name:
                        skipped_count += 1
                        continue

                    # Clean Price
                    raw_price = item.get("price", "0")
                    # Remove currency symbols and non-numeric chars except dot/comma
                    clean_price = "".join(c for c in raw_price if c.isdigit() or c in ".,")
                    if "," in clean_price and "." in clean_price:
                        # assume 1.234,56 -> 1234.56
                        clean_price = clean_price.replace(".", "").replace(",", ".")
                    elif "," in clean_price:
                        # assume 12,34 -> 12.34
                        clean_price = clean_price.replace(",", ".")

                    price = Decimal(clean_price) if clean_price else Decimal("0")

                    description = item.get("description", "")
                    category_name = item.get("category_search_term", "Uncategorized").title()

                    # Handle Category
                    if category_name not in category_cache:
                        cat_slug = slugify(category_name)
                        category, created = Category.objects.get_or_create(
                            slug=cat_slug, defaults={"name": category_name}
                        )
                        category_cache[category_name] = category
                    else:
                        category = category_cache[category_name]

                    # Create Product
                    # Check duplicates by name?
                    product, created = Product.objects.get_or_create(
                        name=name,
                        seller=seller,
                        defaults={
                            "category": category,
                            "description": description,
                            "price": price,
                            "stock_quantity": random.randint(5, 50),
                            "is_active": True,
                            # 'specifications': {'original_url': item.get('product_url')} # Optional if model supports JSON
                        },
                    )

                    if not created:
                        # Update fields if needed, or skip
                        # For now, just skip heavy updates, maybe update price
                        pass

                    # Handle Images
                    # 'images' is a list of local paths
                    image_paths = item.get("images", [])
                    # If 'images' is empty/null, check 'image' (main image)
                    if not image_paths and item.get("image"):
                        image_paths = [item.get("image")]

                    for img_path in image_paths:
                        if not img_path:
                            continue

                        # The path in JSON is absolute or relative to where script ran.
                        # We need to ensure we can read it.
                        if os.path.exists(img_path):
                            # Check if this image is already attached (deduplication by filename logic is hard without hashing)
                            # We'll just add it if product was created, or if it has no images
                            if created or not product.images.exists():
                                with open(img_path, "rb") as img_f:
                                    # Create Django file object
                                    django_file = File(img_f)

                                    ProductImage.objects.create(
                                        product=product,
                                        image=django_file,  # Django handles saving to media root
                                        alt_text=f"{name} image",
                                        is_primary=(img_path == image_paths[0]),  # First one is primary
                                    )
                        else:
                            self.stdout.write(self.style.WARNING(f"Image file not found: {img_path}"))

                    success_count += 1
                    if success_count % 10 == 0:
                        self.stdout.write(f"Imported {success_count} products...")

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to import item '{item.get('name', 'Unknown')}': {e}"))
                    skipped_count += 1

        self.stdout.write(self.style.SUCCESS(f"Import complete. Imported: {success_count}, Skipped: {skipped_count}"))
