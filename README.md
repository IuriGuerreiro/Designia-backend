# Designia Backend - Django REST API

A comprehensive Django REST API backend for the Designia marketplace platform, featuring payment processing, order management, and automated task scheduling.

## 🏗 Architecture

The backend follows a **Layered Service Architecture** using Django 5.2 and Django REST Framework.

-   **Core Framework**: Django 5.2 (Python 3.12)
-   **API**: Django REST Framework (DRF) for REST endpoints.
-   **Real-time**: Django Channels + Redis for WebSockets (Chat).
-   **Async Tasks**: Celery + Redis for background processing (Payments, Analytics).
-   **Database**: MySQL 8.0 (Primary), Redis (Cache/Broker).
-   **Storage**: MinIO (S3-compatible) for file storage.
-   **Observability**: Prometheus (Metrics), Grafana (Visualization), Jaeger (Tracing), Kong (Gateway).

### Key Services (Django Apps)
-   **Authentication**: JWT-based auth, Google OAuth, Stripe Connect onboarding.
-   **Marketplace**: Product catalog, search, reviews, order management.
-   **Payment System**: Stripe integration, webhooks, transaction handling.
-   **Chat**: Real-time messaging between users.
-   **AR**: 3D model management for the mobile app.

## 🚀 Quick Start with Docker

The project uses Docker to spin up all infrastructure dependencies (Database, Cache, Storage, Monitoring).

### 1. Prerequisites
-   Docker & Docker Compose
-   Python 3.12+ (for local Django dev)
-   Stripe Account (for payments)

### 2. Network Setup
Create a shared network for the containers:
```bash
docker network create app-network
```

### 3. Core Infrastructure (MySQL, Redis, MinIO)
Start the essential services for development:
```bash
docker-compose -f docker-compose.dev.yml up -d
```
*   **MySQL**: Port 3308 (mapped to 3306 inside container)
*   **Redis**: Port 6379
*   **MinIO**: Console at http://localhost:9101, API at 9100

### 4. Observability Stack (Prometheus, Kong, Grafana)
You have two options for the observability stack:

**Option A: Full Stack (Kong Gateway + Observability)**
```bash
docker-compose -f infrastructure/kong/docker-compose.kong.yml up -d
```
*   **Kong Gateway**: http://localhost:8000
*   **Kong Admin**: http://localhost:8001
*   **Grafana**: http://localhost:3001 (User/Pass: admin/admin)
*   **Prometheus**: http://localhost:9090
*   **Jaeger UI**: http://localhost:16686

**Option B: Observability Only (No Gateway)**
```bash
docker-compose -f infrastructure/kong/docker-compose.observability-only.yml up -d
```

## 💻 Local Development Setup

Once Docker containers are running, you can run the Django app locally.

### 1. Environment Setup
```bash
cd Designia-backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configuration
```bash
cp .env.example .env
# Edit .env:
# - Set DB_PORT=3308 (matching docker-compose.dev.yml)
# - Set DB_HOST=127.0.0.1
# - Configure Stripe Keys
```

### 3. Database Initialization
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### 4. Running the Application
Use the standard Django development server:
```bash
python manage.py runserver
```
-   **API**: http://127.0.0.1:8000/api/
-   **Admin**: http://127.0.0.1:8000/admin/
-   **WebSocket**: ws://127.0.0.1:8000/ws/chat/

> **Note**: If you need to test high-concurrency WebSockets or production-like ASGI behavior, you can use `daphne`:
> `daphne -b 0.0.0.0 -p 8001 designiaBackend.asgi:application`

## 🔄 Celery Task System

The backend uses Celery with Redis for asynchronous task processing and scheduling.

### Core Tasks
- **Payment Timeout Check**: Automatically cancels orders after 3-day grace period
- **Exchange Rate Updates**: Daily currency rate synchronization

### Starting Celery Services

Make sure your Redis container is running (Step 3 above).

**Terminal 1: Celery Worker**
```bash
source .venv/bin/activate
celery -A designiaBackend worker -l info
# Keep this running for task processing
```

**Terminal 2: Celery Beat Scheduler**
```bash
source .venv/bin/activate
celery -A designiaBackend beat -l info
# Keep this running for scheduled tasks
```

## 🧹 Code Style & Hooks

This project uses Black, Ruff, and isort with pre-commit to standardize formatting and linting.

Setup once:
```bash
pre-commit install
```

Run manually anytime:
```bash
black .
isort .
ruff check --fix .
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
source .venv/bin/activate
python test_celery_simple.py
```

### Manual Task Execution

**Test Exchange Rate Update:**
```bash
source .venv/bin/activate
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')
django.setup()

from payment_system.Tasks.exchange_rate_tasks import update_exchange_rates_task
result = update_exchange_rates_task()
print('Exchange Rate Result:', result)
"
```

### Debugging Common Issues

**Worker Not Connecting:**
```bash
# Check Redis connection
redis-cli -p 6379 ping
# Should return: PONG
```

## 📊 System Monitoring

### Task Queues
- `payment_tasks`: Payment processing and timeouts
- `marketplace_tasks`: Exchange rates and marketplace operations

### Scheduled Tasks
- **Exchange Rate Update**: Daily at midnight UTC
- **Payment Timeout Check**: Every hour

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

## 🔐 Security Notes

- Never commit `.env` files
- Use environment variables for all secrets
- Stripe webhook endpoints require HTTPS in production
- Redis should be password-protected in production
