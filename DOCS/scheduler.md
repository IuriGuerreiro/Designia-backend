# Celery Scheduler Guide

This backend uses Celery + Redis for background jobs and scheduled maintenance. This guide shows how to start the scheduler, what it runs, and how to manually trigger or debug tasks.

## Prerequisites
- Python venv active: `. .venv/bin/activate`
- Redis running locally: `redis-server` (defaults used if env vars not set)
- Environment (defaults in settings):
  - `CELERY_BROKER_URL=redis://localhost:6379/0`
  - `CELERY_RESULT_BACKEND=redis://localhost:6379/1`

## Start Services (3 terminals)
1) Redis
```bash
redis-server
```
2) Celery worker (queues for payments + marketplace)
```bash
. .venv/bin/activate
celery -A designiaBackend worker -l info -Q payment_tasks,marketplace_tasks
```
3) Celery beat (DB-backed scheduler)
```bash
. .venv/bin/activate
celery -A designiaBackend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Optional: Start the web app (separate)
```bash
. .venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

## What’s Scheduled
Defined in `designiaBackend/celery.py` with routes/queues configured.
- Daily exchange rates (midnight UTC)
  - Task: `payment_system.Tasks.exchange_rate_tasks.update_exchange_rates_task`
  - Queue: `marketplace_tasks`
- Hourly payment timeout checks
  - Task: `payment_system.Tasks.payment_tasks.check_payment_timeouts_task`
  - Queue: `payment_tasks`

### Payment Timeout Handling
- `check_payment_timeouts_task`: finds `pending_payment` orders older than 3 days and cancels them.
- `cancel_expired_order`: cancels the order, sets `payment_status=failed`, restores reserved stock, and cancels non‑terminal payment transactions.

## Manual Triggers (quick fixes)
Trigger tasks asynchronously from a shell while the worker is running.

Run timeout scan now
```bash
. .venv/bin/activate
python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','designiaBackend.settings'); django.setup()
from payment_system.Tasks.payment_tasks import check_payment_timeouts_task
print('Enqueued task id:', check_payment_timeouts_task.delay().id)
PY
```

Cancel one expired order by id
```bash
. .venv/bin/activate
python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','designiaBackend.settings'); django.setup()
from payment_system.Tasks.payment_tasks import cancel_expired_order
ORDER_ID = 'REPLACE-UUID'
print('Enqueued task id:', cancel_expired_order.delay(ORDER_ID).id)
PY
```

Use the scheduler service wrapper
```bash
. .venv/bin/activate
python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','designiaBackend.settings'); django.setup()
from payment_system.services.celery_scheduler_service import CelerySchedulerService
print('Trigger timeouts:', CelerySchedulerService.trigger_manual_update('payment_timeouts'))
print('Trigger exchange:', CelerySchedulerService.trigger_manual_update('exchange_rates'))
print('Status:', CelerySchedulerService.get_task_status())
PY
```

## Seed or Manage Beat Entries (DB)
Create/update the default periodic entries in `django_celery_beat`.
```bash
. .venv/bin/activate
python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','designiaBackend.settings'); django.setup()
from payment_system.services.celery_scheduler_service import CelerySchedulerService
print('Setup:', CelerySchedulerService.setup_default_tasks())
print('Status:', CelerySchedulerService.get_task_status())
PY
```

## Monitoring & Troubleshooting
- Verify Redis: `redis-cli ping` should return `PONG`.
- See registered tasks:
```bash
. .venv/bin/activate
python - <<'PY'
from celery import current_app
print([t for t in current_app.tasks if 'payment_system' in t])
PY
```
- Inspect DB schedules:
```bash
python manage.py shell <<'PY'
from django_celery_beat.models import PeriodicTask
for t in PeriodicTask.objects.all():
    print(t.name, t.enabled, t.task)
PY
```
- Logs: run workers in `-l info`, or tail project logs as configured.
- Optional Flower dashboard:
```bash
. .venv/bin/activate
pip install flower
celery -A designiaBackend flower  # http://localhost:5555
```

## Reference
- Core tasks: `payment_system/Tasks/payment_tasks.py`, `payment_system/Tasks/exchange_rate_tasks.py`
- Celery config: `designiaBackend/celery.py`, `designiaBackend/settings.py`
- Scheduler service: `payment_system/services/celery_scheduler_service.py`
