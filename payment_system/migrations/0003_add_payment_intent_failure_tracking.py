# Generated manually for payment intent failure tracking fields
# Migration for PaymentTracker and PaymentTransaction model updates

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment_system', '0002_alter_payoutitem_unique_together'),
    ]

    operations = [
        # Add payment intent failure tracking fields to PaymentTracker
        migrations.AddField(
            model_name='paymenttracker',
            name='failure_code',
            field=models.CharField(
                blank=True, 
                max_length=50, 
                help_text='Stripe failure code for failed payment intents'
            ),
        ),
        migrations.AddField(
            model_name='paymenttracker',
            name='failure_reason',
            field=models.TextField(
                blank=True, 
                help_text='Detailed failure reason for payment intent failures'
            ),
        ),
        migrations.AddField(
            model_name='paymenttracker',
            name='stripe_error_data',
            field=models.JSONField(
                blank=True, 
                null=True, 
                help_text='Complete Stripe error data for payment intent failures'
            ),
        ),
        migrations.AddField(
            model_name='paymenttracker',
            name='latest_charge_id',
            field=models.CharField(
                blank=True, 
                max_length=255, 
                help_text='Latest charge ID from payment intent'
            ),
        ),
        migrations.AddField(
            model_name='paymenttracker',
            name='payment_method_id',
            field=models.CharField(
                blank=True, 
                max_length=255, 
                help_text='Payment method ID used'
            ),
        ),
        
        # Add payment intent transaction type choice to PaymentTracker
        migrations.AlterField(
            model_name='paymenttracker',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('payment', 'Payment'), 
                    ('refund', 'Refund'), 
                    ('partial_refund', 'Partial Refund'),
                    ('payment_intent', 'Payment Intent'),
                ], 
                default='payment', 
                max_length=20
            ),
        ),
        
        # Add payment failure tracking fields to PaymentTransaction
        migrations.AddField(
            model_name='paymenttransaction',
            name='payment_failure_code',
            field=models.CharField(
                blank=True, 
                max_length=50, 
                help_text='Stripe failure code if payment intent failed'
            ),
        ),
        migrations.AddField(
            model_name='paymenttransaction',
            name='payment_failure_reason',
            field=models.TextField(
                blank=True, 
                help_text='Reason for payment failure from payment intent'
            ),
        ),
    ]