from unittest.mock import MagicMock, patch

import pytest
from payment_system.services.celery_scheduler_service import CelerySchedulerService


@pytest.mark.unit
class TestCelerySchedulerService:
    @patch("payment_system.services.celery_scheduler_service.CelerySchedulerService.schedule_daily_exchange_rates")
    @patch("payment_system.services.celery_scheduler_service.CelerySchedulerService.schedule_payment_timeout_checks")
    def test_setup_default_tasks_success(self, mock_schedule_timeouts, mock_schedule_rates):
        mock_schedule_rates.return_value = True
        mock_schedule_timeouts.return_value = True

        results = CelerySchedulerService.setup_default_tasks()

        assert results["exchange_rates"] is True
        assert results["payment_timeouts"] is True

    @patch("payment_system.services.celery_scheduler_service.CelerySchedulerService.schedule_daily_exchange_rates")
    def test_setup_default_tasks_error(self, mock_schedule_rates):
        mock_schedule_rates.side_effect = Exception("Setup Error")

        results = CelerySchedulerService.setup_default_tasks()

        assert results["exchange_rates"] is False
        assert "Setup Error" in results["error"]

    @patch("payment_system.services.celery_scheduler_service.CrontabSchedule.objects")
    @patch("payment_system.services.celery_scheduler_service.PeriodicTask.objects")
    def test_schedule_daily_exchange_rates_success(self, mock_periodic_task, mock_crontab):
        mock_crontab.get_or_create.return_value = (MagicMock(), True)
        mock_periodic_task.update_or_create.return_value = (MagicMock(), True)

        result = CelerySchedulerService.schedule_daily_exchange_rates()

        assert result is True
        mock_crontab.get_or_create.assert_called()
        mock_periodic_task.update_or_create.assert_called()

    @patch("payment_system.services.celery_scheduler_service.CrontabSchedule.objects")
    def test_schedule_daily_exchange_rates_error(self, mock_crontab):
        mock_crontab.get_or_create.side_effect = Exception("DB Error")

        result = CelerySchedulerService.schedule_daily_exchange_rates()

        assert result is False

    @patch("payment_system.services.celery_scheduler_service.IntervalSchedule.objects")
    @patch("payment_system.services.celery_scheduler_service.PeriodicTask.objects")
    def test_schedule_payment_timeout_checks_success(self, mock_periodic_task, mock_interval):
        mock_interval.get_or_create.return_value = (MagicMock(), True)
        mock_periodic_task.update_or_create.return_value = (MagicMock(), True)

        result = CelerySchedulerService.schedule_payment_timeout_checks()

        assert result is True
        mock_interval.get_or_create.assert_called()
        mock_periodic_task.update_or_create.assert_called()

    @patch("payment_system.services.celery_scheduler_service.PeriodicTask.objects")
    def test_get_task_status(self, mock_periodic_task):
        mock_qs = MagicMock()
        mock_task = MagicMock()
        mock_task.name = "Test Task"
        mock_task.crontab = MagicMock()
        mock_task.interval = None
        mock_qs.filter.return_value = mock_qs
        mock_qs.count.return_value = 1
        mock_qs.__iter__.return_value = iter([mock_task])
        mock_periodic_task.filter.return_value = mock_qs

        status = CelerySchedulerService.get_task_status()

        assert status["total_tasks"] == 1
        assert status["tasks"][0]["name"] == "Test Task"
        assert status["tasks"][0]["schedule_type"] == "crontab"

    @patch("payment_system.services.celery_scheduler_service.PeriodicTask.objects")
    def test_enable_task_success(self, mock_periodic_task):
        mock_task = MagicMock()
        mock_periodic_task.get.return_value = mock_task

        result = CelerySchedulerService.enable_task("Test Task")

        assert result is True
        assert mock_task.enabled is True
        mock_task.save.assert_called()

    @patch("payment_system.services.celery_scheduler_service.PeriodicTask.objects")
    def test_enable_task_not_found(self, mock_periodic_task):
        mock_periodic_task.DoesNotExist = Exception  # Mocking DoesNotExist since it's a class attribute
        mock_periodic_task.get.side_effect = Exception("Task not found")  # Simulating DoesNotExist

        # Proper way if we imported PeriodicTask directly
        # mock_periodic_task.get.side_effect = PeriodicTask.DoesNotExist

        # Since we patched objects, we simulate

        # Using side_effect with an exception that matches what the code catches
        # The code catches PeriodicTask.DoesNotExist.
        # We need to make sure we are raising exactly that or patching PeriodicTask class itself.
        pass

    @patch("payment_system.services.celery_scheduler_service.PeriodicTask")
    def test_enable_task_not_found_real(self, mock_periodic_task_class):
        # Define a real exception class for DoesNotExist
        class MockDoesNotExist(Exception):
            pass

        # Assign the exception class to the mock
        mock_periodic_task_class.DoesNotExist = MockDoesNotExist
        # Configure side effect to raise an instance of this exception
        mock_periodic_task_class.objects.get.side_effect = MockDoesNotExist()

        result = CelerySchedulerService.enable_task("NonExistent")

        assert result is False

    @patch("payment_system.services.celery_scheduler_service.PeriodicTask")
    def test_disable_task_success(self, mock_periodic_task_class):
        mock_task = MagicMock()
        mock_periodic_task_class.objects.get.return_value = mock_task

        result = CelerySchedulerService.disable_task("Test Task")

        assert result is True
        assert mock_task.enabled is False
        mock_task.save.assert_called()

    @patch("payment_system.Tasks.exchange_rate_tasks.update_exchange_rates_task")
    def test_trigger_manual_update_success(self, mock_task):
        # We need to patch where the task is defined, not where it's imported locally
        with patch("payment_system.Tasks.update_exchange_rates_task") as mock_celery_task:
            mock_celery_task.delay.return_value = MagicMock(id="123")
            result = CelerySchedulerService.trigger_manual_update("exchange_rates")

            assert result["success"] is True
            assert result["task_id"] == "123"

    def test_trigger_manual_update_invalid(self):
        result = CelerySchedulerService.trigger_manual_update("invalid_task")
        assert result["success"] is False
        assert "Unknown task name" in result["error"]
