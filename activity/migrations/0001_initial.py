# Generated manually for activity app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('marketplace', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserClick',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('view', 'Product View'), ('favorite', 'Add to Favorites'), ('unfavorite', 'Remove from Favorites'), ('cart_add', 'Add to Cart'), ('cart_remove', 'Remove from Cart'), ('click', 'Product Click')], max_length=20)),
                ('session_key', models.CharField(blank=True, max_length=40, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('referer', models.URLField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activity_clicks', to='marketplace.product')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='activity_clicks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ActivitySummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_type', models.CharField(choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')], max_length=10)),
                ('period_start', models.DateTimeField()),
                ('period_end', models.DateTimeField()),
                ('total_views', models.PositiveIntegerField(default=0)),
                ('total_clicks', models.PositiveIntegerField(default=0)),
                ('total_favorites', models.PositiveIntegerField(default=0)),
                ('total_unfavorites', models.PositiveIntegerField(default=0)),
                ('total_cart_additions', models.PositiveIntegerField(default=0)),
                ('total_cart_removals', models.PositiveIntegerField(default=0)),
                ('unique_users', models.PositiveIntegerField(default=0)),
                ('unique_sessions', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activity_summaries', to='marketplace.product')),
            ],
            options={
                'ordering': ['-period_start'],
            },
        ),
        migrations.AddIndex(
            model_name='userclick',
            index=models.Index(fields=['product', 'action', 'created_at'], name='activity_us_product_f79df3_idx'),
        ),
        migrations.AddIndex(
            model_name='userclick',
            index=models.Index(fields=['user', 'action', 'created_at'], name='activity_us_user_id_31a8a8_idx'),
        ),
        migrations.AddIndex(
            model_name='userclick',
            index=models.Index(fields=['session_key', 'action', 'created_at'], name='activity_us_session_d9f9e7_idx'),
        ),
        migrations.AddIndex(
            model_name='userclick',
            index=models.Index(fields=['created_at'], name='activity_us_created_b96f92_idx'),
        ),
        migrations.AddIndex(
            model_name='activitysummary',
            index=models.Index(fields=['product', 'period_type', 'period_start'], name='activity_ac_product_dc04b5_idx'),
        ),
        migrations.AddIndex(
            model_name='activitysummary',
            index=models.Index(fields=['period_start', 'period_end'], name='activity_ac_period__ab4f9b_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='activitysummary',
            unique_together={('product', 'period_type', 'period_start')},
        ),
    ]