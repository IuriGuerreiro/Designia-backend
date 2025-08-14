# Generated migration for updating hold period to 30 days

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment_system', '0003_alter_paymenthold_hold_days_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymenthold',
            name='hold_days',
            field=models.PositiveIntegerField(default=30, help_text='Fixed 30-day hold period for all purchases'),
        ),
    ]