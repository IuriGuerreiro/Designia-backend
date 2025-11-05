# Generated manually for S3 presigned URL implementation
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0014_remove_productfavorite_marketplace_productfavorite_created_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="s3_key",
            field=models.CharField(blank=True, max_length=500, help_text="S3 object key for the image"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="s3_bucket",
            field=models.CharField(blank=True, max_length=100, help_text="S3 bucket name"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="original_filename",
            field=models.CharField(blank=True, max_length=255, help_text="Original filename"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="file_size",
            field=models.PositiveIntegerField(blank=True, null=True, help_text="File size in bytes"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="content_type",
            field=models.CharField(blank=True, max_length=100, help_text="MIME type"),
        ),
        migrations.AlterField(
            model_name="productimage",
            name="image",
            field=models.ImageField(blank=True, upload_to="products/"),
        ),
    ]
