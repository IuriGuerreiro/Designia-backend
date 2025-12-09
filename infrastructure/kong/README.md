# Kong API Gateway Infrastructure

Complete Kong Gateway setup with observability stack for Designia authentication service.

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose installed
- Shared Docker network for Django app

### Setup Steps

**1. Create shared network (if not exists):**
```bash
docker network create app-network
```

**2. Start Kong infrastructure:**
```bash
cd infrastructure/kong
docker-compose -f docker-compose.kong.yml up -d
```

**3. Verify Kong is running:**
```bash
# Check Kong health
curl -i http://localhost:8001/status

# Check services
curl -i http://localhost:8001/services
```

**4. Access UIs:**
- **Kong Admin API:** http://localhost:8001
- **Kong Proxy:** http://localhost:8000
- **Jaeger UI:** http://localhost:16686 (Distributed Tracing)
- **Prometheus:** http://localhost:9090 (Metrics)
- **Grafana:** http://localhost:3001 (admin/admin)

---

## 📦 What's Included

### Services

**Kong Gateway** (`localhost:8000`)
- API Gateway with routing and rate limiting
- JWT validation at edge
- Prometheus metrics export

**Kong Admin API** (`localhost:8001`)
- REST API for Kong configuration
- Manage routes, services, plugins

**PostgreSQL** (internal)
- Kong's datastore
- Stores routes, services, plugins config

**Jaeger** (`localhost:16686`)
- Distributed tracing backend
- Visualize request flows across services
- Find performance bottlenecks

**Prometheus** (`localhost:9090`)
- Metrics collection and storage
- Scrapes Kong and Django metrics
- Query language (PromQL)

**Grafana** (`localhost:3001`)
- Metrics visualization
- Pre-configured dashboards
- Alerts and notifications

---

## 🔧 Configuration

### Kong Routes Configuration

Routes are configured via Kong Admin API or declarative config (`kong.yml`).

**Using Admin API:**
```bash
# Create authentication service
curl -X POST http://localhost:8001/services \
  --data name=authentication \
  --data url=http://django:8000

# Create login route with rate limiting
curl -X POST http://localhost:8001/services/authentication/routes \
  --data paths[]=/api/auth/login \
  --data methods[]=POST

# Add rate limiting plugin
curl -X POST http://localhost:8001/routes/{route-id}/plugins \
  --data name=rate-limiting \
  --data config.minute=5
```

**Using Declarative Config:**
Edit `kong.yml` and reload:
```bash
docker exec kong-gateway kong reload
```

### Rate Limiting Defaults

- **Login:** 5 requests/minute
- **Register:** 3 requests/minute
- **Profile:** 60 requests/minute
- **Seller Apply:** 2 requests/hour

### JWT Validation

JWT validation happens at Kong (edge) before reaching Django:

```bash
# Add JWT plugin to protected routes
curl -X POST http://localhost:8001/routes/{route-id}/plugins \
  --data name=jwt \
  --data config.key_claim_name=sub \
  --data config.claims_to_verify=exp
```

Django JWT signing key must match Kong's validation key.

---

## 📊 Monitoring & Observability

### Jaeger - Distributed Tracing

View traces in Jaeger UI: http://localhost:16686

**Example trace:**
```
Request: POST /api/auth/login
├─ Kong Gateway (1ms)
├─ Django Request Middleware (2ms)
├─ AuthService.login (18ms)
│  ├─ Database Query: SELECT user (5ms)
│  ├─ Password Verification (8ms)
│  └─ JWT Token Generation (5ms)
└─ Response (1ms)

Total: 22ms
```

### Prometheus Metrics

Query metrics in Prometheus: http://localhost:9090

**Example queries:**
```promql
# Total login attempts
auth_login_total

# Failed login rate
rate(auth_login_failed[5m])

# 95th percentile latency
histogram_quantile(0.95, auth_login_duration_seconds_bucket)

# Kong request rate
rate(kong_http_requests_total[1m])
```

### Grafana Dashboards

Access Grafana: http://localhost:3001 (admin/admin)

**Pre-configured dashboards:**
- Kong Gateway Overview
- Authentication Service Metrics
- Request Latency Distribution
- Error Rate Tracking

---

## 🧪 Testing Kong Setup

### Test Public Route (No Auth)
```bash
# Should work - no JWT required
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

### Test Protected Route (JWT Required)
```bash
# Without JWT - should return 401
curl -X GET http://localhost:8000/api/auth/profile

# With JWT - should work
curl -X GET http://localhost:8000/api/auth/profile \
  -H "Authorization: Bearer <your-jwt-token>"
```

### Test Rate Limiting
```bash
# Make 6 login requests quickly - 6th should be rate limited
for i in {1..6}; do
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@test.com","password":"test"}'
  echo ""
done

# Should see: 429 Too Many Requests
```

---

## 🔒 Security Considerations

### Internal Endpoints
**IMPORTANT:** Internal API endpoints should NOT be exposed through Kong:
- `/internal/auth/*` - Internal service-to-service only
- Only accessible within Docker network

**Kong should only route:**
- `/api/auth/*` - Public/protected authentication API

### JWT Secret
Make sure Django and Kong use the same JWT secret:
```python
# Django settings.py
SIMPLE_JWT = {
    'SIGNING_KEY': settings.SECRET_KEY,
    'ALGORITHM': 'HS256',
}
```

### Network Isolation
- Kong and Django on shared `app-network`
- Internal services not exposed to host
- Use Docker secrets for production

---

## 🐛 Troubleshooting

### Kong won't start
```bash
# Check logs
docker logs kong-gateway

# Common issues:
# - PostgreSQL not ready → wait for health check
# - Port already in use → change port mappings
# - Migrations failed → run migrations manually
docker exec kong-gateway kong migrations bootstrap
```

### Routes not working
```bash
# List all routes
curl http://localhost:8001/routes

# Check service status
curl http://localhost:8001/services/authentication

# Test backend directly (bypass Kong)
curl http://localhost:8000/api/auth/login
```

### Metrics not appearing
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Verify Kong metrics endpoint
curl http://localhost:8100/metrics

# Verify Django metrics endpoint
curl http://localhost:8000/api/auth/metrics
```

### Tracing not showing
```bash
# Check Jaeger health
curl http://localhost:16686

# Verify OpenTelemetry configuration in Django
# Check logs for trace export errors
```

---

## 📈 Performance Tuning

### Kong Connection Pooling
```yaml
# kong.yml
services:
  - name: authentication-service
    url: http://django:8000
    retries: 5
    connect_timeout: 60000
    write_timeout: 60000
    read_timeout: 60000
```

### Prometheus Retention
```yaml
# prometheus.yml
global:
  scrape_interval: 15s  # Increase for less overhead

# Add retention flags
command:
  - '--storage.tsdb.retention.time=30d'
  - '--storage.tsdb.retention.size=50GB'
```

### Jaeger Sampling
Adjust sampling rate for high-traffic environments:
```python
# Django settings
OTEL_TRACES_SAMPLER = "parentbased_traceidratio"
OTEL_TRACES_SAMPLER_ARG = "0.1"  # Sample 10% of requests
```

---

## 🚀 Production Deployment

For production deployment:

1. **Use Kubernetes** - See `DEPLOYMENT.md` for K8s manifests
2. **Enable HTTPS** - Configure TLS certificates in Kong
3. **Use Redis for rate limiting** - Replace local policy with Redis
4. **Scale Kong** - Run multiple Kong instances behind load balancer
5. **Secure Admin API** - Restrict access to Kong Admin API
6. **Use managed services** - Consider managed Prometheus, Jaeger

---

## 📚 Additional Resources

- [Kong Documentation](https://docs.konghq.com/)
- [Kong Rate Limiting Plugin](https://docs.konghq.com/hub/kong-inc/rate-limiting/)
- [Kong JWT Plugin](https://docs.konghq.com/hub/kong-inc/jwt/)
- [Prometheus Queries](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Jaeger Getting Started](https://www.jaegertracing.io/docs/latest/getting-started/)

---

**Need help?** Check the main [DEPLOYMENT.md](../../authentication/DEPLOYMENT.md) or [API_GATEWAY.md](../../authentication/API_GATEWAY.md)
