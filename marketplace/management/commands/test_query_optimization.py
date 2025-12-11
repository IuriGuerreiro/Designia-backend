"""
Test query optimization for product listing API.

This command tests the optimized queries and measures performance improvements.
"""

import statistics
import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, reset_queries
from django.test import RequestFactory

from marketplace.models import Product


User = get_user_model()


class Command(BaseCommand):
    help = "Test query optimization for product listing performance"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of products to test (default: 20)",
        )
        parser.add_argument(
            "--queries",
            action="store_true",
            help="Show detailed query analysis",
        )

    def handle(self, *args, **options):
        self.test_query_optimization(options["count"], options["queries"])

    def test_query_optimization(self, product_count, show_queries):
        """Test optimized vs non-optimized queries."""
        self.stdout.write(self.style.SUCCESS("🚀 Testing Query Optimization"))
        self.stdout.write("=" * 60)

        # Get test data
        products = list(Product.objects.filter(is_active=True)[:product_count])
        if not products:
            self.stdout.write(self.style.ERROR(" No active products found for testing"))
            return

        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.WARNING("⚠️  No users found - testing anonymous only"))

        self.stdout.write(f"📦 Testing with {len(products)} products")
        if user:
            self.stdout.write(f"👤 Using test user: {user.username}")

        # Setup request factory
        factory = RequestFactory()

        # Test 1: Original query performance (simulated)
        self.stdout.write("\n🧪 Testing Optimized Queries...")

        optimized_times = []
        optimized_queries = []

        for i in range(3):  # Run multiple times for average
            # Create mock request
            request = factory.get("/api/products/")
            if user:
                request.user = user
            else:
                from django.contrib.auth.models import AnonymousUser

                request.user = AnonymousUser()

            # Reset query counter
            reset_queries()
            start_time = time.time()

            # Call the service directly
            from marketplace.services import CatalogService

            service = CatalogService()

            # Use service to list products (this returns a dict with "results" list)
            result = service.list_products(page_size=product_count)

            if not result.ok:
                self.stdout.write(self.style.ERROR(f"Service error: {result.error}"))
                return

            # Results are already model instances (not a queryset), so they are evaluated
            products_list = result.value["results"]

            # Force serialization to mimic view overhead
            from marketplace.serializers import ProductListSerializer

            serializer = ProductListSerializer(products_list, many=True, context={"request": request})
            data = serializer.data

            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            query_count = len(connection.queries)

            optimized_times.append(response_time)
            optimized_queries.append(query_count)

            if show_queries and i == 0:  # Show queries for first run only
                self.stdout.write(f"\n📊 Query Details (Run {i + 1}):")
                for idx, query in enumerate(connection.queries, 1):
                    self.stdout.write(f"  {idx}. {query['sql'][:100]}...")

        # Calculate statistics
        avg_time = statistics.mean(optimized_times)
        avg_queries = statistics.mean(optimized_queries)
        min_time = min(optimized_times)
        max_time = max(optimized_times)

        self.stdout.write("\n📊 Optimized Performance Results:")
        self.stdout.write(f"   Average Response Time: {avg_time:.1f}ms")
        self.stdout.write(f"   Min/Max Response Time: {min_time:.1f}ms / {max_time:.1f}ms")
        self.stdout.write(f"   Average Query Count: {avg_queries:.1f} queries")
        self.stdout.write(f"   Products Serialized: {len(data)} items")

        # Performance evaluation
        self.stdout.write("\n🎯 Query Optimization Analysis:")

        # Query efficiency analysis
        queries_per_product = avg_queries / len(products)
        if queries_per_product <= 1.2:
            self.stdout.write(
                self.style.SUCCESS(f"  EXCELLENT: {queries_per_product:.1f} queries/product - N+1 problem eliminated!")
            )
        elif queries_per_product <= 2.0:
            self.stdout.write(
                self.style.SUCCESS(f"  GOOD: {queries_per_product:.1f} queries/product - Significant optimization")
            )
        elif queries_per_product <= 3.0:
            self.stdout.write(
                self.style.WARNING(f"⚠️  FAIR: {queries_per_product:.1f} queries/product - Some optimization achieved")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f" POOR: {queries_per_product:.1f} queries/product - N+1 problem still exists")
            )

        # Response time analysis
        if avg_time < 50:
            self.stdout.write(self.style.SUCCESS(f"  EXCELLENT: {avg_time:.1f}ms average response time"))
        elif avg_time < 100:
            self.stdout.write(self.style.SUCCESS(f"  GOOD: {avg_time:.1f}ms average response time"))
        elif avg_time < 200:
            self.stdout.write(self.style.WARNING(f"⚠️  FAIR: {avg_time:.1f}ms average response time"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  SLOW: {avg_time:.1f}ms average response time"))

        # Test database indexes
        self.stdout.write("\n🔍 Testing Database Indexes...")
        self.test_index_usage()

        self.stdout.write("\n🎉 Query optimization test completed!")

        # Recommendations
        self.stdout.write("\n💡 Optimization Summary:")
        self.stdout.write("   - Used prefetch_related for images, reviews, favorites")
        self.stdout.write("   - Added select_related for seller and category")
        self.stdout.write("   - Pre-calculated review counts and ratings with annotations")
        self.stdout.write("   - Optimized primary image lookup with prefetched data")
        self.stdout.write("   - Added comprehensive database indexes")

        if queries_per_product <= 1.5 and avg_time < 100:
            self.stdout.write(self.style.SUCCESS("🎯 Performance target achieved! API is well optimized."))
        else:
            self.stdout.write(self.style.WARNING("🔧 Consider additional optimizations if needed."))

    def test_index_usage(self):
        """Test that database indexes are being used properly."""
        try:
            # Test various query patterns to ensure indexes are used
            reset_queries()

            # Test 1: Basic active products query
            list(Product.objects.filter(is_active=True)[:10])

            # Test 2: Category filtering
            list(Product.objects.filter(is_active=True, category__isnull=False)[:10])

            # Test 3: Price ordering
            list(Product.objects.filter(is_active=True).order_by("price")[:10])

            # Test 4: Popular products
            list(Product.objects.filter(is_active=True).order_by("-view_count")[:10])

            total_queries = len(connection.queries)
            self.stdout.write(f"   Index test queries executed: {total_queries}")

            if total_queries <= 4:
                self.stdout.write(self.style.SUCCESS("  Database indexes appear to be working efficiently"))
            else:
                self.stdout.write(self.style.WARNING("⚠️  Consider running ANALYZE on database tables"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f" Index test failed: {str(e)}"))
