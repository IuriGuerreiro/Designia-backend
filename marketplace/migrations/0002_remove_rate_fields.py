# Generated migration to remove rate fields from ProductMetrics

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='productmetrics',
            name='view_to_click_rate',
        ),
        migrations.RemoveField(
            model_name='productmetrics',
            name='click_to_cart_rate',
        ),
        migrations.RemoveField(
            model_name='productmetrics',
            name='cart_to_purchase_rate',
        ),
    ]