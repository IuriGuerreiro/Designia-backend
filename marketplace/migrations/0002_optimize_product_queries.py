# Generated migration for product query optimizations

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Migration to add database indexes for better product listing performance.
    This migration adds composite indexes for the most common query patterns.
    """

    dependencies = [
        ('marketplace', '0001_initial'),
    ]

    operations = [
        # Add performance indexes to Product model using Django's migrations.AddIndex
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-created_at'], name='marketplace_product_active_created_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', 'price'], name='marketplace_product_active_price_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-view_count'], name='marketplace_product_active_views_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-favorite_count'], name='marketplace_product_active_favorites_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['category', 'is_active', '-created_at'], name='marketplace_product_category_active_created_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['seller', 'is_active', '-created_at'], name='marketplace_product_seller_active_created_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['brand', 'is_active'], name='marketplace_product_brand_active_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['condition', 'is_active'], name='marketplace_product_condition_active_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['stock_quantity', 'is_active'], name='marketplace_product_stock_active_idx'),
        ),
        
        # Add indexes to ProductFavorite model
        migrations.AddIndex(
            model_name='productfavorite',
            index=models.Index(fields=['user', 'product'], name='marketplace_productfavorite_user_product_idx'),
        ),
        migrations.AddIndex(
            model_name='productfavorite',
            index=models.Index(fields=['product'], name='marketplace_productfavorite_product_idx'),
        ),
        migrations.AddIndex(
            model_name='productfavorite',
            index=models.Index(fields=['user'], name='marketplace_productfavorite_user_idx'),
        ),
        migrations.AddIndex(
            model_name='productfavorite',
            index=models.Index(fields=['-created_at'], name='marketplace_productfavorite_created_idx'),
        ),
        
        # Add indexes to ProductImage model for primary image lookups
        migrations.AddIndex(
            model_name='productimage',
            index=models.Index(fields=['product', '-is_primary', 'order', 'created_at'], name='marketplace_productimage_product_primary_idx'),
        ),
        
        # Add indexes to ProductReview model for rating calculations
        migrations.AddIndex(
            model_name='productreview',
            index=models.Index(fields=['product', 'is_active', 'rating'], name='marketplace_productreview_product_active_idx'),
        ),
    ]