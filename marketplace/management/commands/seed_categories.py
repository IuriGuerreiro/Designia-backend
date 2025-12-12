import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from marketplace.models import Category


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seeds initial categories into the database."

    def handle(self, *args, **options):
        categories_to_seed = ["Sofa", "Bed", "Dining Table", "Desk", "Floor Lamp", "Rug", "Armchair", "Bookshelf"]

        self.stdout.write(self.style.SUCCESS("Seeding categories..."))

        created_count = 0
        with transaction.atomic():
            for category_name in categories_to_seed:
                slug = slugify(category_name)
                category, created = Category.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "name": category_name,
                        "description": f"Category for {category_name.lower()} items",
                        "is_active": True,
                    },
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created category: {category.name}"))
                    created_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"Category already exists: {category.name}"))

        self.stdout.write(self.style.SUCCESS(f"Category seeding complete. Created {created_count} categories."))
