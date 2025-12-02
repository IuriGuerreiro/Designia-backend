# Phase 3: Selective Microservices Extraction

**Phase Duration**: 6 months (Months 7-12)
**Prerequisites**: Phase 2 Complete (Bounded Contexts Established)
**Goal**: Extract ONLY services with clear scaling needs

## ⚠️ Important Decision Point

**Before proceeding with this phase, answer these questions:**

1. **Do we have performance bottlenecks that can't be solved by horizontal scaling the monolith?**
2. **Do different parts of the system have significantly different scaling needs?**
3. **Do we have 5+ development teams working independently?**
4. **Is operational complexity manageable (DevOps team, monitoring, deployment pipeline)?**

**If you answered NO to most questions → STOP. Stay with modular monolith.**

**Benefits of Modular Monolith**:
- ✅ Simple deployment
- ✅ Easy debugging
- ✅ Fast development
- ✅ Lower operational costs
- ✅ Can still scale horizontally (load balancer + multiple instances)

---

## Table of Contents

1. [Extraction Strategy](#extraction-strategy)
2. [Service Candidates](#service-candidates)
3. [Implementation Plan](#implementation-plan)
4. [Infrastructure Requirements](#infrastructure-requirements)
5. [Migration Guide](#migration-guide)

---

## Extraction Strategy

### Extraction Criteria

**Only extract a service if it meets 3+ of these criteria:**

| Criterion | Weight | Example |
|-----------|--------|---------|
| **High volume** | Critical | 1M+ requests/day |
| **Different scaling needs** | Critical | Needs more CPU/memory than other services |
| **Independent deployment required** | High | Needs weekly updates while monolith updates monthly |
| **Team ownership** | Medium | Dedicated team for this domain |
| **Technology diversity** | Low | Needs different language/framework |
| **Data isolation** | Medium | Sensitive data requiring separate database |

### Extraction Order (Priority)

1. **Activity Service** ✅ (Extract FIRST)
   - Stateless, high volume
   - Low coupling
   - Good learning opportunity

2. **AR Service** ✅ (Extract SECOND)
   - Isolated functionality
   - No dependencies

3. **Catalog Service** ⚠️ (Extract ONLY if needed)
   - Read-heavy (can cache)
   - May benefit from dedicated search engine

**DO NOT Extract (Keep in Monolith)**:
- ❌ Orders Service (complex distributed transactions)
- ❌ Payment Service (requires PCI compliance, complex orchestration)
- ❌ Cart Service (simple, low volume)
- ❌ Identity/Auth Service (shared by all, critical path)

---

## Service Candidates

### 1. Activity Service (First Extraction)

**Why Extract?**
- ✅ High volume (user tracking events)
- ✅ Stateless (no complex business logic)
- ✅ Different scaling needs (writes >> reads)
- ✅ Low risk (failure doesn't affect core business)

**Current State**:
```python
# activity/models.py
class UserClick(models.Model):
    user = models.ForeignKey(User, ...)
    action = models.CharField(max_length=50)
    product = models.ForeignKey(Product, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Target Architecture**:
```
Client → API Gateway → Activity Microservice
                         ↓
                     TimescaleDB / ClickHouse
                         ↓
                     Analytics Pipeline
```

**Technology Stack**:
- **Framework**: FastAPI (Python) or Go (higher performance)
- **Database**: TimescaleDB (time-series) or ClickHouse (analytics)
- **Message Queue**: RabbitMQ or Kafka for event ingestion
- **Deployment**: Docker + Kubernetes

---

### 2. AR Service (Second Extraction)

**Why Extract?**
- ✅ Isolated functionality (3D model management)
- ✅ No business logic dependencies
- ✅ Can use specialized infrastructure (GPU for processing)

**Current State**:
```python
# ar/models.py
class ProductARModel(models.Model):
    product = models.ForeignKey(Product, ...)
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    s3_key = models.CharField(max_length=500)
```

**Target Architecture**:
```
Client → API Gateway → AR Microservice
                         ↓
                     S3 (3D models)
                         ↓
                     Processing Queue (Celery/RabbitMQ)
```

**Technology Stack**:
- **Framework**: FastAPI or Django (keep familiar)
- **Storage**: S3 + CDN
- **Processing**: Celery workers with GPU support
- **Deployment**: Docker + Kubernetes

---

### 3. Catalog Service (Optional)

**Why Consider?**
- ⚠️ Read-heavy (10:1 read/write ratio)
- ⚠️ Can benefit from dedicated search (Elasticsearch)
- ⚠️ May need different caching strategy

**When to Extract**:
- Product catalog > 100K products
- Search performance < 500ms is critical
- Different team owns product management

**When NOT to Extract**:
- Current performance is acceptable
- Can solve with caching (Redis) in monolith
- Team is small (< 5 developers)

---

## Implementation Plan

### Month 7-8: Activity Service Extraction

#### Week 1-2: Service Scaffolding

**Goal**: Create standalone Activity microservice

**Steps**:

1. **Create New Repository**
   ```bash
   mkdir designia-activity-service
   cd designia-activity-service

   # Initialize FastAPI project
   pip install fastapi uvicorn sqlalchemy alembic

   # Project structure
   activity-service/
   ├── app/
   │   ├── api/
   │   │   └── v1/
   │   │       └── endpoints/
   │   │           └── tracking.py
   │   ├── domain/
   │   │   ├── models.py
   │   │   └── services.py
   │   ├── infrastructure/
   │   │   ├── database.py
   │   │   └── messaging.py
   │   └── main.py
   ├── tests/
   ├── Dockerfile
   ├── docker-compose.yml
   └── requirements.txt
   ```

2. **Implement API**

   ```python
   # app/api/v1/endpoints/tracking.py
   from fastapi import APIRouter, Depends
   from app.domain.services import TrackingService

   router = APIRouter()

   @router.post("/track")
   async def track_event(
       event: TrackingEvent,
       service: TrackingService = Depends()
   ):
       """Track user activity event"""
       result = await service.track_event(
           user_id=event.user_id,
           action=event.action,
           product_id=event.product_id,
           metadata=event.metadata
       )

       return {"status": "success", "event_id": result.event_id}

   @router.get("/user/{user_id}/activity")
   async def get_user_activity(
       user_id: str,
       service: TrackingService = Depends()
   ):
       """Get user activity history"""
       events = await service.get_user_activity(user_id, limit=100)
       return {"events": events}
   ```

3. **Setup Database**

   ```python
   # app/infrastructure/database.py
   from sqlalchemy import create_engine
   from sqlalchemy.ext.declarative import declarative_base
   from sqlalchemy.orm import sessionmaker

   SQLALCHEMY_DATABASE_URL = "postgresql://user:pass@localhost/activity_db"

   engine = create_engine(SQLALCHEMY_DATABASE_URL)
   SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
   Base = declarative_base()

   def get_db():
       db = SessionLocal()
       try:
           yield db
       finally:
           db.close()
   ```

4. **Docker Configuration**

   ```dockerfile
   # Dockerfile
   FROM python:3.11-slim

   WORKDIR /app

   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   COPY ./app /app

   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
   ```

**Deliverables**:
- Standalone Activity microservice
- API documentation (OpenAPI/Swagger)
- Docker image
- Integration tests

---

#### Week 3-4: Dual-Write Pattern

**Goal**: Write to both monolith AND microservice

**Strategy**: Gradual migration with rollback capability

**Step 1: Add Feature Flag**

```python
# settings.py
USE_ACTIVITY_MICROSERVICE = os.getenv('USE_ACTIVITY_MICROSERVICE', 'false').lower() == 'true'
ACTIVITY_SERVICE_URL = os.getenv('ACTIVITY_SERVICE_URL', 'http://activity-service:8080')
```

**Step 2: Create Adapter**

```python
# utils/activity_adapter.py
import requests
from django.conf import settings

class ActivityAdapter:
    """Adapter to write to both systems during migration"""

    def __init__(self):
        self.use_microservice = settings.USE_ACTIVITY_MICROSERVICE
        self.service_url = settings.ACTIVITY_SERVICE_URL

    def track_event(self, user_id, action, product_id=None, metadata=None):
        """Track event in both systems"""

        # Always write to monolith (source of truth during migration)
        from activity.models import UserClick
        UserClick.objects.create(
            user_id=user_id,
            action=action,
            product_id=product_id,
            metadata=metadata
        )

        # Also write to microservice if enabled
        if self.use_microservice:
            try:
                response = requests.post(
                    f"{self.service_url}/api/v1/track",
                    json={
                        "user_id": str(user_id),
                        "action": action,
                        "product_id": str(product_id) if product_id else None,
                        "metadata": metadata
                    },
                    timeout=2  # Short timeout - don't block main flow
                )

                if response.status_code != 200:
                    logger.warning(f"Activity microservice error: {response.status_code}")

            except requests.RequestException as e:
                # Don't fail main flow if microservice is down
                logger.exception(f"Failed to track in microservice: {e}")
```

**Step 3: Update Callers**

```python
# marketplace/views.py
from utils.activity_adapter import ActivityAdapter

class ProductViewSet(viewsets.ModelViewSet):
    def retrieve(self, request, pk=None):
        product = self.get_object()

        # Track view using adapter (writes to both systems)
        activity_adapter = ActivityAdapter()
        activity_adapter.track_event(
            user_id=request.user.id if request.user.is_authenticated else None,
            action='product_view',
            product_id=product.id
        )

        serializer = self.get_serializer(product)
        return Response(serializer.data)
```

**Step 4: Data Verification**

```python
# scripts/verify_activity_data.py
from activity.models import UserClick
import requests

def verify_data_consistency():
    """Compare monolith vs microservice data"""

    # Get recent events from monolith
    monolith_events = UserClick.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()

    # Get count from microservice
    response = requests.get(f"{ACTIVITY_SERVICE_URL}/api/v1/stats/hourly")
    microservice_count = response.json()['count']

    # Compare
    difference = abs(monolith_events - microservice_count)
    success_rate = (1 - difference / monolith_events) * 100 if monolith_events > 0 else 0

    print(f"Monolith: {monolith_events}")
    print(f"Microservice: {microservice_count}")
    print(f"Success Rate: {success_rate:.2f}%")

    return success_rate >= 99.0  # 99% consistency required
```

**Deliverables**:
- Dual-write adapter implemented
- Feature flag configured
- Data verification script
- Monitoring dashboards

---

#### Week 5-6: Traffic Migration

**Goal**: Gradually shift reads to microservice

**Migration Steps**:

1. **Phase 1: Dual Write (Week 5)**
   - Write to both systems
   - Read from monolith only
   - Verify 99%+ consistency

2. **Phase 2: Canary Reads (Week 6)**
   - Write to both systems
   - Read from microservice for 10% of traffic
   - Monitor error rates

3. **Phase 3: Full Migration (Month 8)**
   - Write to microservice only
   - Read from microservice
   - Keep monolith as backup for 30 days

**Canary Read Implementation**:

```python
# utils/activity_adapter.py
class ActivityAdapter:
    def get_user_activity(self, user_id, limit=100):
        """Get user activity with canary routing"""

        # Determine routing (10% to microservice)
        if self.use_microservice and random.random() < 0.10:
            try:
                response = requests.get(
                    f"{self.service_url}/api/v1/user/{user_id}/activity",
                    params={"limit": limit},
                    timeout=2
                )

                if response.status_code == 200:
                    return response.json()['events']
            except:
                pass  # Fallback to monolith

        # Fallback or default: read from monolith
        from activity.models import UserClick
        return list(UserClick.objects.filter(user=user_id).order_by('-created_at')[:limit])
```

**Monitoring**:

```python
# Monitor error rates
from prometheus_client import Counter, Histogram

activity_requests = Counter('activity_requests_total', 'Total activity requests', ['source', 'status'])
activity_latency = Histogram('activity_latency_seconds', 'Activity request latency', ['source'])

def track_with_metrics(source, func):
    start = time.time()
    try:
        result = func()
        activity_requests.labels(source=source, status='success').inc()
        return result
    except Exception as e:
        activity_requests.labels(source=source, status='error').inc()
        raise
    finally:
        activity_latency.labels(source=source).observe(time.time() - start)
```

**Rollback Plan**:
```python
# Emergency rollback: disable microservice
# settings.py
USE_ACTIVITY_MICROSERVICE = False
# Deploy change → traffic immediately back to monolith
```

**Deliverables**:
- Canary routing implemented
- Monitoring dashboards (Grafana)
- Error alerting (PagerDuty/Opsgenie)
- Rollback procedure tested

---

#### Week 7-8: Cleanup & Optimization

**Goal**: Remove monolith activity code

**Steps**:

1. **Data Migration**
   ```bash
   # Archive old activity data
   pg_dump activity_db > activity_backup_$(date +%Y%m%d).sql

   # Delete from monolith (after 30-day safety period)
   python manage.py shell
   >>> UserClick.objects.filter(created_at__lt=timezone.now() - timedelta(days=90)).delete()
   ```

2. **Code Removal**
   ```bash
   # Remove activity app from monolith
   rm -rf activity/
   # Update INSTALLED_APPS in settings.py
   # Run tests to ensure no broken imports
   ```

3. **Performance Optimization**
   - Add database indexes
   - Implement caching (Redis)
   - Optimize query patterns
   - Add connection pooling

**Deliverables**:
- Monolith activity code removed
- Microservice optimized
- Documentation updated
- Post-mortem completed

---

### Month 9-10: AR Service Extraction

**Follow same pattern as Activity Service**:

1. Week 1-2: Service scaffolding
2. Week 3-4: Dual-write
3. Week 5-6: Traffic migration
4. Week 7-8: Cleanup

**AR-Specific Considerations**:

- **Large Files**: Implement chunked uploads
- **Processing Queue**: Use Celery for async 3D processing
- **Storage**: S3 + CloudFront CDN
- **Validation**: 3D model format validation (GLTF, OBJ, FBX)

---

### Month 11-12: Infrastructure & Observability

#### Kubernetes Deployment

```yaml
# k8s/activity-service-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: activity-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: activity-service
  template:
    metadata:
      labels:
        app: activity-service
    spec:
      containers:
      - name: activity-service
        image: designia/activity-service:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: activity-db-secret
              key: url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: activity-service
spec:
  selector:
    app: activity-service
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: activity-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: activity-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

#### Service Mesh (Optional)

```yaml
# Istio for advanced traffic management
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: activity-service
spec:
  hosts:
  - activity-service
  http:
  - match:
    - headers:
        canary:
          exact: "true"
    route:
    - destination:
        host: activity-service
        subset: canary
  - route:
    - destination:
        host: activity-service
        subset: stable
```

---

## Infrastructure Requirements

### Minimum Requirements per Microservice

| Resource | Activity | AR | Catalog (if extracted) |
|----------|----------|-----|------------------------|
| **Pods** | 3 | 3 | 5 |
| **Memory** | 256MB | 512MB | 512MB |
| **CPU** | 0.25 | 0.5 | 0.5 |
| **Database** | PostgreSQL | PostgreSQL | PostgreSQL + Elasticsearch |
| **Storage** | N/A | S3 (100GB+) | S3 (500GB+) |
| **Cache** | Redis (1GB) | Redis (2GB) | Redis (5GB) |

### Estimated Costs (AWS)

| Component | Monthly Cost (USD) |
|-----------|-------------------|
| **EKS Cluster** | $73 |
| **EC2 Instances** (t3.medium x 3) | $100 |
| **RDS PostgreSQL** (db.t3.small x 2) | $60 |
| **ElastiCache Redis** | $40 |
| **S3 + CloudFront** | $50 |
| **Monitoring** (CloudWatch, Datadog) | $100 |
| **Load Balancer** | $25 |
| **Total** | **~$450/month** |

**Comparison**:
- Monolith: ~$150/month (single instance + DB)
- Microservices (2 extracted): ~$450/month
- **3x cost increase**

---

## Migration Guide

### Pre-Migration Checklist

- [ ] Modular monolith with bounded contexts
- [ ] 80%+ test coverage
- [ ] Monitoring and alerting in place
- [ ] Feature flags implemented
- [ ] Rollback procedures tested
- [ ] Team trained on Kubernetes
- [ ] DevOps pipeline automated
- [ ] Cost approval obtained

### Post-Migration Checklist

- [ ] All traffic migrated
- [ ] Performance metrics stable
- [ ] Error rates < 0.1%
- [ ] Monolith code removed
- [ ] Documentation updated
- [ ] Post-mortem completed
- [ ] Team retrospective

---

## Success Criteria

### Technical Metrics

- [ ] **Service Independence**: Each service deployable independently
- [ ] **Latency**: < 100ms added per service hop
- [ ] **Availability**: 99.9%+ per service
- [ ] **Error Rate**: < 0.1% per service
- [ ] **Deployment Frequency**: Can deploy service independently 10+ times/week

### Business Metrics

- [ ] **Development Velocity**: Maintained or improved
- [ ] **Incident MTTR**: < 30 minutes
- [ ] **Cost**: Within budget (+50% acceptable)
- [ ] **Team Satisfaction**: Survey score 4+/5

---

## Decision: To Extract or Not to Extract?

### Extract IF:
✅ Clear performance bottleneck in specific service
✅ Service has very different scaling needs
✅ Independent deployment is critical business need
✅ Team > 10 developers, can support operational complexity
✅ Budget for 3x infrastructure costs

### DO NOT Extract IF:
❌ "Everyone else is doing microservices"
❌ Want to learn new technology
❌ Think it will magically solve problems
❌ Team < 5 developers
❌ Performance is acceptable with monolith

**Remember**: Modular monolith gives you 80% of benefits with 20% of complexity.

---

**Document Status**: Complete
**Last Updated**: 2025-11-29
