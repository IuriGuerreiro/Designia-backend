# Migration to add ExchangeRate model for local exchange rate storage

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment_system', '0005_remove_paymenthold_created_by_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExchangeRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_currency', models.CharField(help_text='Base currency code (e.g., USD, EUR)', max_length=3)),
                ('target_currency', models.CharField(help_text='Target currency code (e.g., EUR, GBP)', max_length=3)),
                ('rate', models.DecimalField(decimal_places=6, help_text='Exchange rate from base to target currency', max_digits=12)),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When this rate was recorded')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='When this rate was last updated')),
                ('source', models.CharField(default='manual', help_text='Source of this exchange rate data', max_length=100)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this rate is currently active')),
            ],
            options={
                'verbose_name': 'Exchange Rate',
                'verbose_name_plural': 'Exchange Rates',
                'db_table': 'payment_exchange_rates',
                'ordering': ['-created_at', 'base_currency', 'target_currency'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='exchangerate',
            unique_together={('base_currency', 'target_currency', 'created_at')},
        ),
        migrations.AddIndex(
            model_name='exchangerate',
            index=models.Index(fields=['base_currency', 'target_currency', '-created_at'], name='payment_exc_base_cu_ab5a15_idx'),
        ),
        migrations.AddIndex(
            model_name='exchangerate',
            index=models.Index(fields=['created_at'], name='payment_exc_created_b9b6c4_idx'),
        ),
        migrations.AddIndex(
            model_name='exchangerate',
            index=models.Index(fields=['is_active'], name='payment_exc_is_acti_e92d3e_idx'),
        ),
    ]