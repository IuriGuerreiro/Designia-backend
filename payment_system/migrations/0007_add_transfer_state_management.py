# Generated migration for transfer state management enhancements

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment_system', '0006_add_exchange_rate_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymenttransaction',
            name='transfer_id',
            field=models.CharField(blank=True, db_index=True, help_text='Stripe transfer ID when payment is transferred to seller', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='paymenttransaction',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('held', 'On Hold'), ('processing', 'Processing'), ('completed', 'Completed'), ('released', 'Released to Seller'), ('disputed', 'Disputed'), ('refunded', 'Refunded'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
        migrations.AddIndex(
            model_name='paymenttransaction',
            index=models.Index(fields=['transfer_id'], name='payment_tra_transfe_3f4d8f_idx'),
        ),
    ]