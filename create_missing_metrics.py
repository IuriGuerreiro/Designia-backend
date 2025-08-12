#!/usr/bin/env python3
"""
Utility script to create missing ProductMetrics for existing products.

This script ensures all products have corresponding ProductMetrics records.
Run this script to retroactively create metrics for products that were created
before the comprehensive tracking system was implemented.
"""

import os
import sys
import django
from decimal import Decimal

# Setup Django
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designia_backend.settings')

try:
    django.setup()
    
    from marketplace.models import Product, ProductMetrics
    from django.db import transaction
    
    print("=== CREATING MISSING PRODUCT METRICS ===")
    
    # Get all products
    all_products = Product.objects.all()
    print(f"Found {all_products.count()} total products")
    
    # Get products without metrics
    products_with_metrics = ProductMetrics.objects.values_list('product_id', flat=True)
    products_without_metrics = all_products.exclude(id__in=products_with_metrics)
    
    print(f"Found {products_without_metrics.count()} products without metrics")
    
    if products_without_metrics.count() == 0:
        print("✅ All products already have ProductMetrics!")
        sys.exit(0)
    
    # Create missing metrics in batch
    with transaction.atomic():
        metrics_to_create = []
        
        for product in products_without_metrics:
            metrics_to_create.append(ProductMetrics(
                product=product,
                total_views=0,
                total_clicks=0,
                total_favorites=0,
                total_cart_additions=0,
                total_sales=0,
                total_revenue=Decimal('0.00'),
            ))
        
        # Bulk create all missing metrics
        created_metrics = ProductMetrics.objects.bulk_create(
            metrics_to_create,
            ignore_conflicts=True,
            batch_size=1000
        )
        
        print(f"✅ Successfully created {len(created_metrics)} ProductMetrics records")
    
    # Verify all products now have metrics
    products_still_missing = Product.objects.exclude(
        id__in=ProductMetrics.objects.values_list('product_id', flat=True)
    ).count()
    
    if products_still_missing == 0:
        print("🎉 All products now have ProductMetrics!")
    else:
        print(f"⚠️  {products_still_missing} products still missing metrics")
    
    print("\n=== SUMMARY ===")
    print(f"Total products: {Product.objects.count()}")
    print(f"Total ProductMetrics: {ProductMetrics.objects.count()}")
    print("✅ ProductMetrics creation completed successfully!")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)