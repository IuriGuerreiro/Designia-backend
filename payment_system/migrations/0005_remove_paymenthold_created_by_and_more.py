# Simplified migration to fix payment system consolidation

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('payment_system', '0004_update_hold_period_to_30_days'),
    ]

    operations = [
        # First, add new fields to PaymentTransaction
        migrations.AddField(
            model_name='paymenttransaction',
            name='hold_reason',
            field=models.CharField(choices=[('standard', 'Standard Hold Period'), ('new_seller', 'New Seller Verification'), ('high_value', 'High Value Transaction'), ('suspicious', 'Suspicious Activity'), ('dispute', 'Dispute Filed'), ('manual', 'Manual Hold')], default='standard', max_length=20),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='days_to_hold',
            field=models.PositiveIntegerField(default=30, help_text='Number of days to hold payment (default: 30)'),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='hold_start_date',
            field=models.DateTimeField(blank=True, help_text='When hold period started', null=True),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='planned_release_date',
            field=models.DateTimeField(blank=True, help_text='Calculated release date', null=True),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='actual_release_date',
            field=models.DateTimeField(blank=True, help_text='When payment was actually released', null=True),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='hold_notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='released_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='released_payment_transactions', to=settings.AUTH_USER_MODEL),
        ),

        # Migrate data from PaymentHold to PaymentTransaction (if any exist)
        migrations.RunSQL(
            """
            UPDATE payment_transactions 
            SET 
                hold_reason = COALESCE(
                    (SELECT reason FROM payment_holds WHERE payment_transaction_id = payment_transactions.id), 
                    'standard'
                ),
                days_to_hold = COALESCE(
                    (SELECT hold_days FROM payment_holds WHERE payment_transaction_id = payment_transactions.id), 
                    30
                ),
                hold_start_date = COALESCE(
                    (SELECT hold_start_date FROM payment_holds WHERE payment_transaction_id = payment_transactions.id),
                    payment_received_date,
                    created_at
                ),
                planned_release_date = COALESCE(
                    (SELECT planned_release_date FROM payment_holds WHERE payment_transaction_id = payment_transactions.id),
                    datetime(COALESCE(payment_received_date, created_at), '+30 days')
                ),
                actual_release_date = (SELECT actual_release_date FROM payment_holds WHERE payment_transaction_id = payment_transactions.id),
                hold_notes = COALESCE(
                    (SELECT hold_notes FROM payment_holds WHERE payment_transaction_id = payment_transactions.id),
                    'Standard 30-day hold period'
                ),
                released_by_id = (SELECT released_by_id FROM payment_holds WHERE payment_transaction_id = payment_transactions.id);
            """,
            reverse_sql=migrations.RunSQL.noop
        ),

        # Remove old field
        migrations.RemoveField(
            model_name='paymenttransaction',
            name='hold_release_date',
        ),

        # Clean up foreign key relationships before deleting models
        migrations.RunSQL(
            "DELETE FROM payment_holds;",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            "DELETE FROM payment_items;",  
            reverse_sql=migrations.RunSQL.noop
        ),
        
        # Delete old models
        migrations.DeleteModel(name='PaymentHold'),
        migrations.DeleteModel(name='PaymentItem'),
    ]
