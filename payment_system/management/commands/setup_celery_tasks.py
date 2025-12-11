"""
Management command to set up Celery periodic tasks for the payment system.

This command configures all default periodic tasks including:
- Daily exchange rate updates
- Payment timeout checks
- Database maintenance tasks
"""

from django.core.management.base import BaseCommand, CommandError

from payment_system.services.celery_scheduler_service import CelerySchedulerService


class Command(BaseCommand):
    help = "Set up default Celery periodic tasks for the payment system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--exchange-hour",
            type=int,
            default=0,
            help="Hour for daily exchange rate update (0-23, default: 0 for midnight UTC)",
        )
        parser.add_argument(
            "--exchange-minute", type=int, default=0, help="Minute for daily exchange rate update (0-59, default: 0)"
        )
        parser.add_argument(
            "--timeout-interval", type=int, default=1, help="Hours between payment timeout checks (default: 1)"
        )
        parser.add_argument("--force", action="store_true", help="Force update of existing tasks")
        parser.add_argument(
            "--status-only", action="store_true", help="Show current task status without making changes"
        )

    def handle(self, *args, **options):
        """Set up Celery periodic tasks."""

        if options["status_only"]:
            self.show_task_status()
            return

        self.stdout.write(self.style.SUCCESS("Setting up Celery periodic tasks..."))

        try:
            # Setup default tasks with provided options
            results = self._setup_tasks_with_options(options)

            # Display results
            self.display_results(results)

            # Show final status
            self.show_task_status()

            self.stdout.write(
                self.style.SUCCESS(
                    "\n  Celery task setup completed successfully!\n"
                    "Start Celery worker and beat scheduler:\n"
                    "  celery -A designiaBackend worker -l info -Q payment_tasks,marketplace_tasks\n"
                    "  celery -A designiaBackend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler"
                )
            )

        except Exception as e:
            raise CommandError(f"Failed to set up Celery tasks: {e}") from e

    def _setup_tasks_with_options(self, options):
        """Set up tasks with command line options."""
        results = {}

        # Exchange rate updates
        self.stdout.write("Setting up daily exchange rate updates...")
        results["exchange_rates"] = CelerySchedulerService.schedule_daily_exchange_rates(
            hour=options["exchange_hour"], minute=options["exchange_minute"]
        )

        # Payment timeout checks
        self.stdout.write("Setting up payment timeout checks...")
        results["payment_timeouts"] = CelerySchedulerService.schedule_payment_timeout_checks(
            interval_hours=options["timeout_interval"]
        )

        return results

    def display_results(self, results):
        """Display setup results."""
        self.stdout.write("\n📋 Task Setup Results:")

        for task_name, success in results.items():
            if success:
                self.stdout.write(f"    {task_name.replace('_', ' ').title()}: {self.style.SUCCESS('Configured')}")
            else:
                self.stdout.write(f"   {task_name.replace('_', ' ').title()}: {self.style.ERROR('Failed')}")

    def show_task_status(self):
        """Show current status of all tasks."""
        self.stdout.write("\n📊 Current Task Status:")

        try:
            status = CelerySchedulerService.get_task_status()

            if "error" in status:
                self.stdout.write(f"   Error getting status: {self.style.ERROR(status['error'])}")
                return

            self.stdout.write(f"  📈 Total tasks: {status['total_tasks']}")
            self.stdout.write(f"    Enabled tasks: {status['enabled_tasks']}")
            self.stdout.write(f"   Disabled tasks: {status['disabled_tasks']}")

            # Show individual task details
            if status["tasks"]:
                self.stdout.write("\n📝 Task Details:")
                for task in status["tasks"]:
                    status_icon = " " if task["enabled"] else "❌"
                    last_run = task["last_run_at"] or "Never"

                    self.stdout.write(
                        f"  {status_icon} {task['name']}:\n"
                        f"      Schedule: {task.get('schedule', 'Unknown')}\n"
                        f"      Last run: {last_run}\n"
                        f"      Run count: {task['total_run_count']}"
                    )
            else:
                self.stdout.write("  No tasks found.")

        except Exception as e:
            self.stdout.write(f"   Error getting task status: {self.style.ERROR(str(e))}")

    def handle_celery_status(self):
        """Show Celery worker status."""
        self.stdout.write("\n🔧 Celery Status Check:")

        try:
            from celery import current_app

            # Check if Celery is configured
            broker_url = current_app.conf.broker_url
            result_backend = current_app.conf.result_backend

            self.stdout.write(f"  Broker URL: {broker_url}")
            self.stdout.write(f"  Result Backend: {result_backend}")

            # Try to get worker stats (this will only work if workers are running)
            try:
                inspect = current_app.control.inspect()
                stats = inspect.stats()
                if stats:
                    self.stdout.write(f"  Active workers: {len(stats)}")
                    for worker_name in stats.keys():
                        self.stdout.write(f"    - {worker_name}")
                else:
                    self.stdout.write("  ⚠️  No active workers found")
            except Exception:
                self.stdout.write("  ⚠️  Could not connect to workers (they may not be running)")

        except Exception as e:
            self.stdout.write(f"   Celery configuration error: {e}")
