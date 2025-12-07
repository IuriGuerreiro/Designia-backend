import statistics
import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, reset_queries
from django.test import RequestFactory

from marketplace.tests.factories import CategoryFactory, ProductFactory, UserFactory

# Import Views
from marketplace.views.product_views import ProductViewSet as NewProductViewSet
from marketplace.views_legacy import ProductViewSet as LegacyProductViewSet

User = get_user_model()


class Command(BaseCommand):
    help = "Benchmark Legacy vs New Implementation"

    def add_arguments(self, parser):
        parser.add_argument("--iterations", type=int, default=100, help="Number of iterations")
        parser.add_argument("--products", type=int, default=50, help="Number of products to create")

    def handle(self, *args, **options):
        iterations = options["iterations"]
        product_count = options["products"]

        self.stdout.write(self.style.SUCCESS("🚀 Starting Performance Benchmark"))
        self.stdout.write(f"   Iterations: {iterations}")
        self.stdout.write(f"   Products: {product_count}")

        # Setup Data
        self.stdout.write("📦 Setting up test data...")
        user = UserFactory()
        category = CategoryFactory()
        products = ProductFactory.create_batch(product_count, category=category, is_active=True)
        self.stdout.write("   Data created.")

        factory = RequestFactory()
        request = factory.get("/api/products/")
        request.user = user

        # Define Scenarios
        scenarios = [
            ("Legacy Product List", LegacyProductViewSet, {"get": "list"}, {}),
            ("New Product List", NewProductViewSet, {"get": "list"}, {}),
            ("Legacy Product Detail", LegacyProductViewSet, {"get": "retrieve"}, {"pk": products[0].pk}),
            (
                "New Product Detail",
                NewProductViewSet,
                {"get": "retrieve"},
                {"slug": products[0].slug},
            ),  # New uses slug lookup
        ]

        results = {}

        for name, view_class, actions, kwargs in scenarios:
            self.stdout.write(f"\n🧪 Benchmarking: {name}")

            # Warmup
            view = view_class.as_view(actions)
            try:
                view(request, **kwargs)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   Warmup failed: {e}"))
                continue

            times = []
            queries = []

            for _ in range(iterations):
                reset_queries()
                start = time.perf_counter()

                view(request, **kwargs)

                end = time.perf_counter()
                times.append((end - start) * 1000)  # ms
                queries.append(len(connection.queries))

            avg_time = statistics.mean(times)
            p95_time = statistics.quantiles(times, n=20)[18]  # 95th percentile
            avg_queries = statistics.mean(queries)

            results[name] = {"avg_ms": avg_time, "p95_ms": p95_time, "queries": avg_queries}

            self.stdout.write(f"   Avg: {avg_time:.2f}ms | P95: {p95_time:.2f}ms | Queries: {avg_queries:.1f}")

        # Compare
        self.stdout.write("\n📊 Comparison Report")
        self.stdout.write("=" * 60)
        self.stdout.write(f"{'Metric':<25} | {'Legacy':<10} | {'New':<10} | {'Diff':<10}")
        self.stdout.write("-" * 60)

        comparisons = [
            ("Product List (ms)", "Legacy Product List", "New Product List", "avg_ms"),
            ("Product List (Queries)", "Legacy Product List", "New Product List", "queries"),
            ("Product Detail (ms)", "Legacy Product Detail", "New Product Detail", "avg_ms"),
            ("Product Detail (Queries)", "Legacy Product Detail", "New Product Detail", "queries"),
        ]

        for label, legacy_key, new_key, metric in comparisons:
            if legacy_key not in results or new_key not in results:
                continue

            legacy_val = results[legacy_key][metric]
            new_val = results[new_key][metric]
            diff = ((new_val - legacy_val) / legacy_val) * 100 if legacy_val > 0 else 0

            diff_str = f"{diff:+.1f}%"
            color = self.style.SUCCESS if diff <= 0 else self.style.ERROR
            if metric == "queries" and diff <= 0:
                color = self.style.SUCCESS

            self.stdout.write(f"{label:<25} | {legacy_val:<10.2f} | {new_val:<10.2f} | {color(diff_str)}")

        self.stdout.write("=" * 60)
