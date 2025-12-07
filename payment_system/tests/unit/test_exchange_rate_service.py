from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from payment_system.services.exchange_rate_service import ExchangeRateService


@pytest.mark.unit
class TestExchangeRateService:
    @patch("payment_system.models.ExchangeRate.objects")
    @patch("payment_system.services.exchange_rate_service.ExchangeRateService._fetch_exchange_rates")
    @patch("payment_system.models.ExchangeRate.bulk_create_rates")
    def test_update_exchange_rates_fresh_skip(self, mock_bulk_create, mock_fetch, mock_objects):
        mock_objects.is_data_fresh.return_value = True

        result = ExchangeRateService.update_exchange_rates()

        assert result["success"] is True
        assert result["skipped"] is True
        mock_fetch.assert_not_called()
        mock_bulk_create.assert_not_called()

    @patch("payment_system.models.ExchangeRate.objects")
    @patch("payment_system.services.exchange_rate_service.ExchangeRateService._fetch_exchange_rates")
    @patch("payment_system.models.ExchangeRate.bulk_create_rates")
    def test_update_exchange_rates_force(self, mock_bulk_create, mock_fetch, mock_objects):
        mock_objects.is_data_fresh.return_value = True
        mock_fetch.return_value = {"EUR": 0.85}
        mock_bulk_create.return_value = 1

        result = ExchangeRateService.update_exchange_rates(force_update=True)

        assert result["success"] is True
        assert result["created_count"] == 1
        mock_fetch.assert_called_once()
        mock_bulk_create.assert_called_once()

    @patch("payment_system.models.ExchangeRate.objects")
    @patch("payment_system.services.exchange_rate_service.ExchangeRateService._fetch_exchange_rates")
    def test_update_exchange_rates_fetch_fail(self, mock_fetch, mock_objects):
        mock_objects.is_data_fresh.return_value = False
        mock_fetch.return_value = None

        result = ExchangeRateService.update_exchange_rates()

        assert result["success"] is False
        assert "Failed to fetch" in result["error"]

    @patch("payment_system.services.exchange_rate_service.requests.get")
    def test_fetch_exchange_rates_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"EUR": 0.85}}
        mock_get.return_value = mock_response

        result = ExchangeRateService._fetch_exchange_rates("USD")

        assert result == {"EUR": 0.85}

    @patch("payment_system.services.exchange_rate_service.requests.get")
    def test_fetch_exchange_rates_invalid_json(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "bad api"}  # Missing 'rates'
        mock_get.return_value = mock_response

        result = ExchangeRateService._fetch_exchange_rates("USD")

        assert result is None

    @patch("payment_system.services.exchange_rate_service.requests.get")
    def test_fetch_exchange_rates_network_error(self, mock_get):
        mock_get.side_effect = Exception("Network Error")

        result = ExchangeRateService._fetch_exchange_rates("USD")

        assert result is None

    def test_get_test_data(self):
        data = ExchangeRateService._get_test_data("USD")
        assert "EUR" in data
        assert data["EUR"] == 0.85

        data_eur = ExchangeRateService._get_test_data("EUR")
        assert "USD" in data_eur
        assert data_eur["USD"] == 1.18

    @patch("payment_system.models.ExchangeRate.objects")
    def test_cleanup_old_rates(self, mock_objects):
        mock_objects.filter.return_value.delete.return_value = (5, {})

        count = ExchangeRateService._cleanup_old_rates()

        assert count == 5
        mock_objects.filter.assert_called()

    @patch("payment_system.models.ExchangeRate.objects")
    def test_get_exchange_rate_status_has_data(self, mock_objects):
        mock_rate = MagicMock()
        mock_rate.created_at = timezone.now() - timedelta(hours=1)
        mock_rate.source = "api"

        mock_objects.order_by.return_value.first.return_value = mock_rate
        mock_objects.filter.return_value.count.return_value = 10

        status = ExchangeRateService.get_exchange_rate_status()

        assert status["has_data"] is True
        assert status["is_fresh"] is True
        assert status["total_rates"] == 10

    @patch("payment_system.models.ExchangeRate.objects")
    def test_get_exchange_rate_status_no_data(self, mock_objects):
        mock_objects.order_by.return_value.first.return_value = None

        status = ExchangeRateService.get_exchange_rate_status()

        assert status["has_data"] is False
        assert status["status"] == "no_data"

    @patch("payment_system.services.exchange_rate_service.ExchangeRateService.get_exchange_rate_status")
    @patch("payment_system.services.exchange_rate_service.ExchangeRateService.update_exchange_rates")
    def test_force_update_if_stale_needed(self, mock_update, mock_status):
        mock_status.return_value = {"has_data": True, "age_hours": 25}  # Stale

        ExchangeRateService.force_update_if_stale()

        mock_update.assert_called_with(force_update=True, source="auto_stale_check")

    @patch("payment_system.services.exchange_rate_service.ExchangeRateService.get_exchange_rate_status")
    @patch("payment_system.services.exchange_rate_service.ExchangeRateService.update_exchange_rates")
    def test_force_update_if_stale_not_needed(self, mock_update, mock_status):
        mock_status.return_value = {"has_data": True, "age_hours": 1}  # Fresh

        result = ExchangeRateService.force_update_if_stale()

        assert result["skipped"] is True
        mock_update.assert_not_called()
