# Generated manually for PaymentTracker payout status choices
# Run this migration: python manage.py migrate payment_system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment_system', '0006_paymenttracker_stripe_transfer_id_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymenttracker',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('succeeded', 'Succeeded'),
                    ('failed', 'Failed'),
                    ('canceled', 'Canceled'),
                    ('refunded', 'Refunded'),
                    ('partially_refunded', 'Partially Refunded'),
                    ('payout_processing', 'Payout Processing'),
                    ('payout_success', 'Payout Success'),
                    ('payout_failed', 'Payout Failed'),
                ],
                default='pending',
                max_length=20
            ),
        ),
    ]