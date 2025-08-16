"""
Django management command to update exchange rates daily.
Usage: python manage.py update_exchange_rates
"""
import requests
import time
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from payment_system.models import ExchangeRate
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update exchange rates from external API and store in database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-currency',
            type=str,
            default='USD',
            help='Base currency for exchange rates (default: USD)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if data is fresh',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old exchange rate data after update',
        )
        parser.add_argument(
            '--test-data',
            action='store_true',
            help='Create test exchange rate data instead of fetching from API',
        )

    def handle(self, *args, **options):
        base_currency = options['base_currency'].upper()
        force_update = options['force']
        cleanup_old = options['cleanup']
        use_test_data = options['test_data']
        
        self.stdout.write(
            self.style.SUCCESS(f'🔄 Starting exchange rate update for {base_currency}')
        )
        
        # Check if update is needed
        if not force_update and not use_test_data:
            if ExchangeRate.objects.is_data_fresh():
                self.stdout.write(
                    self.style.WARNING('⏭️  Exchange rate data is fresh, skipping update. Use --force to override.')
                )
                return
        
        try:
            if use_test_data:
                rates_data = self.create_test_data(base_currency)
                source = 'test_data'
            else:
                rates_data = self.fetch_exchange_rates(base_currency)
                source = 'free_api'
            
            if not rates_data:
                raise CommandError('❌ Failed to fetch exchange rate data')
            
            # Store rates in database
            created_count = ExchangeRate.bulk_create_rates(
                base_currency=base_currency,
                rates_dict=rates_data,
                source=source
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Created {created_count} exchange rates for {base_currency}')
            )
            
            # Cleanup old data if requested
            if cleanup_old:
                deleted_count = self.cleanup_old_rates()
                self.stdout.write(
                    self.style.SUCCESS(f'🗑️  Cleaned up {deleted_count} old exchange rate records')
                )
            
            # Display summary
            self.display_summary(base_currency)
            
        except Exception as e:
            logger.error(f"Exchange rate update failed: {e}")
            raise CommandError(f'❌ Exchange rate update failed: {str(e)}')

    def fetch_exchange_rates(self, base_currency):
        """
        Fetch exchange rates from a free API.
        Using exchangerate-api.com which provides free rates without API key.
        """
        try:
            # Free API endpoint - no API key required
            url = f'https://api.exchangerate-api.com/v4/latest/{base_currency}'
            
            self.stdout.write(f'📡 Fetching rates from: {url}')
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if 'rates' not in data:
                raise CommandError('Invalid response format from exchange rate API')
            
            rates = data['rates']
            
            self.stdout.write(f'📊 Fetched {len(rates)} exchange rates')
            
            return rates
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch exchange rates: {e}")
            self.stdout.write(
                self.style.ERROR(f'❌ Network error: {str(e)}')
            )
            return None
        except Exception as e:
            logger.error(f"Error processing exchange rate data: {e}")
            self.stdout.write(
                self.style.ERROR(f'❌ Data processing error: {str(e)}')
            )
            return None

    def create_test_data(self, base_currency):
        """
        Create test exchange rate data for development/testing.
        """
        self.stdout.write('🧪 Creating test exchange rate data')
        
        # Sample exchange rates (these are approximate and for testing only)
        test_rates = {
            'USD': {
                'EUR': 0.85,
                'GBP': 0.73,
                'JPY': 110.0,
                'CAD': 1.25,
                'AUD': 1.35,
                'CHF': 0.92,
                'CNY': 6.45,
                'SEK': 8.5,
                'NOK': 8.8,
                'DKK': 6.3,
                'PLN': 3.9,
                'CZK': 21.5,
                'HUF': 295.0,
                'RUB': 75.0,
                'BRL': 5.2,
                'INR': 74.0,
                'KRW': 1180.0,
                'SGD': 1.35,
                'HKD': 7.8,
                'MXN': 20.1,
                'TRY': 8.5,
                'ZAR': 14.5,
                'THB': 31.5,
                'MYR': 4.1,
                'PHP': 49.5,
                'IDR': 14250.0,
                'VND': 22800.0,
            },
            'EUR': {
                'USD': 1.18,
                'GBP': 0.86,
                'JPY': 129.0,
                'CAD': 1.47,
                'AUD': 1.59,
                'CHF': 1.08,
                'CNY': 7.6,
                'SEK': 10.0,
                'NOK': 10.4,
                'DKK': 7.4,
            }
        }
        
        if base_currency in test_rates:
            return test_rates[base_currency]
        else:
            # Return USD rates converted to the base currency
            usd_rates = test_rates['USD']
            if base_currency in usd_rates:
                base_to_usd = usd_rates[base_currency]
                converted_rates = {}
                for currency, rate in usd_rates.items():
                    if currency != base_currency:
                        converted_rates[currency] = rate / base_to_usd
                return converted_rates
            else:
                # Fallback: return a subset of major currencies
                return {
                    'USD': 1.0,
                    'EUR': 0.85,
                    'GBP': 0.73,
                    'JPY': 110.0,
                }

    def cleanup_old_rates(self, keep_days=7):
        """
        Clean up old exchange rate data.
        """
        try:
            cutoff_date = timezone.now() - timezone.timedelta(days=keep_days)
            deleted_count = ExchangeRate.objects.filter(
                created_at__lt=cutoff_date
            ).delete()[0]
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old rates: {e}")
            return 0

    def display_summary(self, base_currency):
        """
        Display a summary of current exchange rate data.
        """
        try:
            # Get latest rates
            latest_rates = ExchangeRate.objects.get_latest_rates(base_currency)
            
            if latest_rates:
                latest_update = ExchangeRate.objects.order_by('-created_at').first()
                
                self.stdout.write('\n📊 Exchange Rate Summary:')
                self.stdout.write(f'   Base Currency: {base_currency}')
                self.stdout.write(f'   Last Updated: {latest_update.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")}')
                self.stdout.write(f'   Source: {latest_update.source}')
                self.stdout.write(f'   Total Rates: {len(latest_rates)}')
                
                # Show top 10 rates
                self.stdout.write('\n🔝 Top Exchange Rates:')
                sorted_rates = sorted(latest_rates.items(), key=lambda x: x[1], reverse=True)
                for currency, rate in sorted_rates[:10]:
                    self.stdout.write(f'   {base_currency}/{currency}: {rate:.6f}')
                
                if len(sorted_rates) > 10:
                    self.stdout.write(f'   ... and {len(sorted_rates) - 10} more')
            
            # Check data freshness
            is_fresh = ExchangeRate.objects.is_data_fresh()
            freshness_status = '🟢 Fresh' if is_fresh else '🟡 Stale'
            self.stdout.write(f'\n📅 Data Status: {freshness_status}')
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Could not display summary: {str(e)}')
            )

    def success(self, message):
        """Helper method for success messages."""
        self.stdout.write(self.style.SUCCESS(message))

    def error(self, message):
        """Helper method for error messages."""
        self.stdout.write(self.style.ERROR(message))