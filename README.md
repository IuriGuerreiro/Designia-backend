# Designia Backend - Django REST API

A comprehensive Django REST API backend for the Designia marketplace platform, featuring payment processing, order management, and automated task scheduling.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- ngrok (for webhook testing)
- Stripe Account (for payments)

### Installation

1. **Clone and Setup**
```bash
cd Designia-backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Environment Configuration**
```bash
cp .env.example .env
# Edit .env with your actual values:
# - Database credentials
# - Stripe API keys
# - Redis configuration
# - Email settings
```

3. **Database Setup**
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

4. **Redis Server**
```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis

# macOS
brew install redis
brew services start redis

# Windows (WSL recommended)
# Install Redis in WSL following Ubuntu instructions above
```

### Running the Application

1. **Start Daphne Server**
```bash
# Easy way (recommended)
./run_backend.sh          # Linux/macOS
run_backend.bat           # Windows

# Manual way
daphne -b 192.168.3.2 -p 8001 designiaBackend.asgi:application
```

2. **Setup ngrok for Stripe Webhooks**
```bash
# Install ngrok from https://ngrok.com/
ngrok http 8001
# Copy the https://*.ngrok-free.app URL
# Add to Stripe Dashboard > Webhooks with endpoint: /api/payments/stripe_webhook/
```

## 🌐 Access Points

- **API**: http://192.168.3.2:8001/api/
- **Admin**: http://192.168.3.2:8001/admin/
- **WebSocket**: ws://192.168.3.2:8001/ws/chat/

## 🔄 Celery Task System

The backend uses Celery with Redis for asynchronous task processing and scheduling.

### Core Tasks
- **Payment Timeout Check**: Automatically cancels orders after 3-day grace period
- **Exchange Rate Updates**: Daily currency rate synchronization

### Starting Celery Services

**Terminal 1: Redis Server**
```bash
redis-server
# Keep this running
```

**Terminal 2: Celery Worker**
```bash
source venv/bin/activate
celery -A designiaBackend worker -l info
# Keep this running for task processing
```

**Terminal 3: Celery Beat Scheduler**
```bash
source venv/bin/activate
celery -A designiaBackend beat -l info
# Keep this running for scheduled tasks
```

**Terminal 4: Django Server** (optional)
```bash
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

### Celery Monitoring (Optional)
```bash
# Install Flower for web-based monitoring
pip install flower

# Start Flower dashboard
celery -A designiaBackend flower
# Access at http://localhost:5555
```

## 🧪 Testing & Debugging Celery

### Quick Connectivity Test
```bash
source venv/bin/activate
python test_celery_simple.py
```
This tests:
- Worker connectivity
- Task registration
- Exchange rate updates
- Payment timeout processing
- Scheduler status

### Manual Task Execution

**Test Exchange Rate Update:**
```bash
source venv/bin/activate
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.Tasks.exchange_rate_tasks import update_exchange_rates_task
result = update_exchange_rates_task()
print('Exchange Rate Result:', result)
"
```

**Test Payment Timeout Check:**
```bash
source venv/bin/activate
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.Tasks.payment_tasks import check_payment_timeouts_task
result = check_payment_timeouts_task()
print('Timeout Check Result:', result)
"
```

**Manual Payment Timeout Test:**
```bash
source venv/bin/activate
python test_manual_timeout.py
```

### Trigger Tasks via Service Layer
```python
from payment_system.services.celery_scheduler_service import CelerySchedulerService

# Trigger immediate execution
exchange_result = CelerySchedulerService.trigger_manual_update('exchange_rates')
timeout_result = CelerySchedulerService.trigger_manual_update('payment_timeouts')

# Check task status
status = CelerySchedulerService.get_task_status()
print(status)
```

### Debugging Common Issues

**Worker Not Connecting:**
```bash
# Check Redis connection
redis-cli ping
# Should return: PONG

# Check Celery configuration
python -c "from celery import current_app; print(current_app.conf.broker_url)"
```

**Tasks Not Registered:**
```bash
# List all registered tasks
python -c "
from celery import current_app
tasks = list(current_app.tasks.keys())
payment_tasks = [t for t in tasks if 'payment_system' in t]
print('Payment Tasks:', payment_tasks)
"
```

**Clear Redis Queue (Reset):**
```bash
# Clear all queues and results
redis-cli FLUSHALL

# Or clear specific queues
redis-cli DEL celery payment_tasks marketplace_tasks
```

**Check Scheduled Tasks:**
```bash
# View Beat scheduler database entries
python manage.py shell
>>> from django_celery_beat.models import PeriodicTask
>>> for task in PeriodicTask.objects.all():
...     print(f"{task.name}: {task.enabled}")
```

## 📊 System Monitoring

### Task Queues
- `payment_tasks`: Payment processing and timeouts
- `marketplace_tasks`: Exchange rates and marketplace operations

### Scheduled Tasks
- **Exchange Rate Update**: Daily at midnight UTC
- **Payment Timeout Check**: Every hour

### Logs
```bash
# View Celery worker logs
tail -f celery_worker.log

# View Django logs
tail -f django_debug.log

# Monitor Redis activity
redis-cli MONITOR
```

## 🛠 Development Workflow

### Adding New Celery Tasks

1. **Create Task Function**
```python
# In payment_system/Tasks/
from celery import shared_task

@shared_task(bind=True, max_retries=3, queue='your_queue')
def your_new_task(self, param):
    # Task implementation
    return {'success': True}
```

2. **Register in __init__.py**
```python
# In payment_system/Tasks/__init__.py
from .your_module import your_new_task

__all__ = [
    'your_new_task',
    # ... other tasks
]
```

3. **Add to Beat Schedule**
```python
# In designiaBackend/celery.py
app.conf.beat_schedule = {
    'your-task-name': {
        'task': 'payment_system.Tasks.your_module.your_new_task',
        'schedule': 60.0 * 60.0,  # Every hour
        'options': {'queue': 'your_queue'}
    }
}
```

### Testing New Tasks
```bash
# Test task directly
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.Tasks.your_module import your_new_task
result = your_new_task()
print(result)
"

# Test via Celery
python -c "
from payment_system.Tasks.your_module import your_new_task
async_result = your_new_task.delay()
print('Task ID:', async_result.id)
print('Result:', async_result.get())
"
```

## 🔐 Security Notes

- Never commit `.env` files
- Use environment variables for all secrets
- Stripe webhook endpoints require HTTPS in production
- Redis should be password-protected in production
- Review Celery security settings for production deployment

## 📦 Key Components

- **Django REST Framework**: API endpoints
- **Celery + Redis**: Asynchronous task processing  
- **Stripe Integration**: Payment processing
- **MySQL/PostgreSQL**: Database
- **JWT Authentication**: User authentication
- **Automated Testing**: Comprehensive test suite

## 🚀 Production Deployment

### Celery in Production
```bash
# Use supervisor or systemd for process management
# Example systemd service files:

# /etc/systemd/system/celery-worker.service
# /etc/systemd/system/celery-beat.service

# Enable and start services
sudo systemctl enable celery-worker celery-beat
sudo systemctl start celery-worker celery-beat
```

### Environment Configuration
- Use Redis with authentication
- Configure proper Django settings for production
- Set up SSL certificates for HTTPS
- Configure firewall rules
- Monitor logs and performance metrics

## 📞 Support

For issues related to:
- **Payment Processing**: Check Stripe dashboard and webhook logs
- **Task Scheduling**: Monitor Celery logs and Redis connectivity  
- **Database**: Review Django migrations and model changes
- **Authentication**: Verify JWT token configuration

## 📋 Task Status Reference

### Task States
- ✅ **SUCCESS**: Task completed successfully
- ❌ **FAILURE**: Task failed with error
- 🔄 **PENDING**: Task queued but not started
- ⏳ **RETRY**: Task retrying after failure
- 📊 **PROGRESS**: Task in progress (custom state)

### Queue Status
- **Active**: Currently processing tasks
- **Scheduled**: Tasks waiting for execution time
- **Failed**: Tasks that exceeded max retries
- **Success**: Successfully completed tasks