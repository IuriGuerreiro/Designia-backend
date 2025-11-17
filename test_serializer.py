import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "designiaBackend.settings")
django.setup()

from marketplace.models import Product  # noqa: E402
from marketplace.serializers import ProductDetailSerializer  # noqa: E402

# Get the first product
product = Product.objects.first()

if product:
    print(f"Testing with product: {product.name} (ID: {product.id})")

    # Check if it has an AR model
    has_ar_attr = hasattr(product, "ar_model")
    print(f"hasattr(product, 'ar_model'): {has_ar_attr}")

    if has_ar_attr:
        print(f"product.ar_model is not None: {product.ar_model is not None}")

    # Now serialize it
    serializer = ProductDetailSerializer(product, context={"request": None})
    data = serializer.data

    print(f"\nSerializer output includes has_ar_model: {'has_ar_model' in data}")
    if "has_ar_model" in data:
        print(f"has_ar_model value: {data['has_ar_model']}")

    print(f"\nAll fields in output: {list(data.keys())}")
else:
    print("No products found in database")
