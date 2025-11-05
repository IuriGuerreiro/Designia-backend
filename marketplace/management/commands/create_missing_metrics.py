"""
Django management command to create missing ProductMetrics for existing products.

Usage:
    python manage.py create_missing_metrics
    python manage.py create_missing_metrics --batch-size 500
    python manage.py create_missing_metrics --dry-run
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from marketplace.models import Product, ProductMetrics


class Command(BaseCommand):
    help = "Create missing ProductMetrics for existing products"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of metrics to create in each batch (default: 1000)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating anything",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        self.stdout.write(self.style.SUCCESS("=== CREATING MISSING PRODUCT METRICS ==="))

        # Get all products
        all_products = Product.objects.all()
        total_products = all_products.count()
        self.stdout.write(f"Found {total_products} total products")

        # Get products without metrics
        products_with_metrics = ProductMetrics.objects.values_list("product_id", flat=True)
        products_without_metrics = all_products.exclude(id__in=products_with_metrics)
        missing_count = products_without_metrics.count()

        self.stdout.write(f"Found {missing_count} products without metrics")

        if missing_count == 0:
            self.stdout.write(self.style.SUCCESS("  All products already have ProductMetrics!"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would create {missing_count} ProductMetrics records"))

            # Show some examples
            examples = products_without_metrics[:5]
            self.stdout.write("Examples of products that would get metrics:")
            for product in examples:
                self.stdout.write(f"  - {product.name} (ID: {product.id})")

            if missing_count > 5:
                self.stdout.write(f"  ... and {missing_count - 5} more")
            return

        # Create missing metrics in batches
        try:
            with transaction.atomic():
                metrics_to_create = []
                created_count = 0

                self.stdout.write(f"Creating metrics in batches of {batch_size}...")

                for i, product in enumerate(products_without_metrics.iterator(), 1):
                    metrics_to_create.append(
                        ProductMetrics(
                            product=product,
                            total_views=0,
                            total_clicks=0,
                            total_favorites=0,
                            total_cart_additions=0,
                            total_sales=0,
                            total_revenue=Decimal("0.00"),
                        )
                    )

                    # Create batch when we reach batch_size or end of products
                    if len(metrics_to_create) >= batch_size or i == missing_count:
                        created_metrics = ProductMetrics.objects.bulk_create(
                            metrics_to_create, ignore_conflicts=True, batch_size=batch_size
                        )
                        created_count += len(created_metrics)
                        metrics_to_create = []  # Reset for next batch

                        self.stdout.write(f"  Created batch: {created_count}/{missing_count} metrics")

                self.stdout.write(self.style.SUCCESS(f"  Successfully created {created_count} ProductMetrics records"))

        except Exception as e:
            raise CommandError(f"Error creating ProductMetrics: {str(e)}") from e

        # Verify all products now have metrics
        products_still_missing = Product.objects.exclude(
            id__in=ProductMetrics.objects.values_list("product_id", flat=True)
        ).count()

        if products_still_missing == 0:
            self.stdout.write(self.style.SUCCESS("🎉 All products now have ProductMetrics!"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {products_still_missing} products still missing metrics"))

        # Final summary
        self.stdout.write("\n=== SUMMARY ===")
        self.stdout.write(f"Total products: {Product.objects.count()}")
        self.stdout.write(f"Total ProductMetrics: {ProductMetrics.objects.count()}")
        self.stdout.write(self.style.SUCCESS("  ProductMetrics creation completed successfully!"))
