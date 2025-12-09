# Kong + Observability Stack - Quick Start Guide

**Phase 3: API Gateway Integration & Observability**

Complete setup for production-ready authentication service with Kong Gateway, distributed tracing, and metrics.

---

## 🚀 Quick Start (5 minutes)

### Step 1: Install Dependencies

```bash
cd Designia-backend
pip install -r requirements.txt
```

New dependencies added:
- `opentelemetry-api` - Tracing API
- `opentelemetry-sdk` - Tracing SDK
- `opentelemetry-instrumentation-django` - Auto-instrumentation for Django
- `opentelemetry-exporter-jaeger` - Jaeger exporter
- `prometheus-client` - Metrics collection

### Step 2: Update Environment Variables

Add to your `.env` file (see `.env.example` for full list):

```bash
# OpenTelemetry Tracing
OTEL_TRACING_ENABLED=True
JAEGER_AGENT_HOST=localhost
JAEGER_AGENT_PORT=6831

# Internal service URLs
AUTHENTICATION_INTERNAL_URL=http://localhost:8000/internal/auth
```

### Step 3: Start Kong + Observability Stack

```bash
cd infrastructure/kong
docker-compose -f docker-compose.kong.yml up -d
```

This starts:
- **Kong Gateway** (ports 8000, 8001, 8100)
- **PostgreSQL** (Kong's database)
- **Jaeger** (distributed tracing)
- **Prometheus** (metrics collection)
- **Grafana** (metrics visualization)

### Step 4: Verify Services

```bash
# Check Kong health
curl http://localhost:8001/status

# Check Jaeger
curl http://localhost:16686

# Check Prometheus
curl http://localhost:9090

# Check Django health
curl http://localhost:8000/api/auth/health/live/
curl http://localhost:8000/api/auth/health/ready/
```

### Step 5: Access UIs

- **Jaeger Tracing:** http://localhost:16686
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3001 (admin/admin)
- **Kong Admin API:** http://localhost:8001

---

## 📊 What Was Built

### 1. **OpenTelemetry Distributed Tracing**

**Location:** `authentication/infra/observability/tracing.py`

Automatically traces all Django requests and exports to Jaeger.

**Usage in code:**
```python
from authentication.infra.observability import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("user_id", user.id)
    # Your code here
```

**View traces:**
- Visit http://localhost:16686
- Select "authentication-service"
- Search for traces

### 2. **Prometheus Metrics**

**Location:** `authentication/infra/observability/metrics.py`

Comprehensive metrics for monitoring authentication service.

**Available metrics:**
- `auth_login_total` - Total login attempts (by status, requires_2fa)
- `auth_login_failed` - Failed logins (by reason)
- `auth_login_duration_seconds` - Login latency histogram
- `auth_seller_applications_total` - Seller applications
- `auth_jwt_validation_total` - JWT validations
- ... and many more

**View metrics:**
- Endpoint: http://localhost:8000/api/auth/metrics
- Prometheus UI: http://localhost:9090
- Grafana dashboards: http://localhost:3001

### 3. **Internal API Endpoints**

**Location:** `authentication/api/views/internal_views.py`

Service-to-service communication endpoints (NOT exposed through Kong).

**Endpoints:**
- `GET /internal/auth/users/{user_id}/` - Get user by ID
- `POST /internal/auth/validate-token/` - Validate JWT token
- `POST /internal/auth/users/batch/` - Batch get users
- `GET /internal/auth/check-email/{email}/` - Check email existence

**Usage from other services:**
```python
import requests

# Get user data
response = requests.get(
    'http://localhost:8000/internal/auth/users/123e4567-e89b-12d3-a456-426614174000/'
)
user_data = response.json()
```

### 4. **Health Check Endpoints**

**Location:** `authentication/api/views/health_views.py`

Kubernetes-compatible health probes.

**Endpoints:**
- `GET /api/auth/health/live/` - Liveness probe (is process alive?)
- `GET /api/auth/health/ready/` - Readiness probe (can handle requests?)

**Readiness checks:**
- Database connection
- Redis connection
- Event bus connection

### 5. **Kong Gateway Configuration**

**Location:** `infrastructure/kong/kong.yml`

Pre-configured routes for authentication service:

**Public routes (no JWT):**
- `POST /api/auth/login` - 5 req/min rate limit
- `POST /api/auth/register` - 3 req/min rate limit
- `POST /api/auth/verify-email`
- `POST /api/auth/google/login`

**Protected routes (JWT required):**
- `GET/PUT /api/auth/profile` - 60 req/min
- `POST /api/auth/seller/apply` - 2 req/hour
- `GET /api/auth/seller/status` - 20 req/min

---

## 🧪 Testing the Setup

### Test 1: Health Checks

```bash
# Liveness (should always return 200)
curl http://localhost:8000/api/auth/health/live/

# Readiness (checks dependencies)
curl http://localhost:8000/api/auth/health/ready/
```

### Test 2: Metrics Endpoint

```bash
# View all metrics
curl http://localhost:8000/api/auth/metrics

# Should see metrics like:
# auth_login_total{status="success",requires_2fa="false"} 5.0
# auth_login_duration_seconds_count 5.0
```

### Test 3: Internal API

```bash
# Test internal user lookup (no auth required)
curl http://localhost:8000/internal/auth/users/YOUR-USER-UUID/

# Test token validation
curl -X POST http://localhost:8000/internal/auth/validate-token/ \
  -H "Content-Type: application/json" \
  -d '{"token": "YOUR-JWT-TOKEN"}'
```

### Test 4: Distributed Tracing

1. Make a login request:
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'
```

2. View the trace in Jaeger:
   - Open http://localhost:16686
   - Select "authentication-service"
   - Click "Find Traces"
   - See the full request flow with timing

---

## 📈 Monitoring Dashboard Setup

### Prometheus Queries (http://localhost:9090)

```promql
# Total login attempts
auth_login_total

# Failed login rate (per 5 minutes)
rate(auth_login_failed[5m])

# 95th percentile login latency
histogram_quantile(0.95, auth_login_duration_seconds_bucket)

# Kong request rate
rate(kong_http_requests_total[1m])
```

### Grafana Dashboard

1. Access Grafana: http://localhost:3001 (admin/admin)
2. Add Prometheus data source (already configured)
3. Create dashboard with panels:
   - Login success rate
   - Login latency (p50, p95, p99)
   - Failed login reasons
   - Active sessions
   - Kong gateway metrics

---

## 🔒 Security Notes

### Internal API Security

**IMPORTANT:** Internal endpoints are NOT authenticated!

- `/internal/auth/*` endpoints have NO authentication
- Should only be accessible within Docker network/Kubernetes cluster
- DO NOT expose through Kong Gateway
- Configure firewall/network policies to restrict access

**Kong routes** (defined in `kong.yml`):
- Only route `/api/auth/*` through gateway
- `/internal/auth/*` is NOT in Kong configuration

### Production Checklist

- [ ] Use Redis for Kong rate limiting (not local)
- [ ] Enable HTTPS with TLS certificates
- [ ] Restrict Kong Admin API access
- [ ] Configure network policies for internal endpoints
- [ ] Use Kubernetes NetworkPolicy for pod-to-pod communication
- [ ] Enable JWT signature verification in Kong
- [ ] Set up Prometheus alerts
- [ ] Configure log aggregation (ELK, Loki)

---

## 🐛 Troubleshooting

### Issue: Kong won't start

```bash
# Check logs
docker logs kong-gateway

# Common fix: Run migrations manually
docker exec kong-gateway kong migrations bootstrap
```

### Issue: Tracing not appearing in Jaeger

```bash
# Check Jaeger health
curl http://localhost:16686

# Check Django logs for trace export errors
docker logs django-container

# Verify Jaeger host in .env
JAEGER_AGENT_HOST=jaeger  # Should match container name
```

### Issue: Metrics endpoint returns empty

```bash
# Generate some traffic first
curl http://localhost:8000/api/auth/login/ -X POST -d '...'

# Then check metrics
curl http://localhost:8000/api/auth/metrics | grep auth_login
```

### Issue: Internal API returns 404

```bash
# Verify URL patterns are loaded
python manage.py show_urls | grep internal

# Should see:
# /internal/auth/users/<uuid:user_id>/ internal_get_user
```

---

## 📚 Next Steps

### Phase 3 Remaining Tasks

✅ **Completed:**
1. Kong Gateway setup with rate limiting
2. OpenTelemetry distributed tracing
3. Prometheus metrics infrastructure
4. Internal API endpoints
5. Health check endpoints
6. Django integration

🔜 **Optional Enhancements:**
- Instrument existing services with tracing spans
- Add more custom metrics
- Create Grafana dashboards
- Set up Prometheus alerts
- Migrate other apps to use internal API

### Production Deployment

See `authentication/DEPLOYMENT.md` (to be created) for:
- Kubernetes manifests
- Helm charts
- Production configuration
- Scaling guidelines

---

## 📖 Documentation

- **Kong Gateway:** [docs.konghq.com](https://docs.konghq.com/)
- **OpenTelemetry:** [opentelemetry.io](https://opentelemetry.io/)
- **Jaeger:** [jaegertracing.io](https://www.jaegertracing.io/)
- **Prometheus:** [prometheus.io](https://prometheus.io/)
- **Grafana:** [grafana.com](https://grafana.com/)

---

**Questions?** Check the main README or tech spec: `docs/sprint-artifacts/tech-spec-authentication-refactoring-phase3.md`
