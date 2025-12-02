# Phase 2: Bounded Contexts & Domain-Driven Design

**Phase Duration**: 3 months (Months 4-6)
**Prerequisites**: Phase 1 Complete (SOLID Score 80+)
**Goal**: Organize code by domain, prepare for microservices extraction

## Table of Contents

1. [Overview](#overview)
2. [Bounded Context Strategy](#bounded-context-strategy)
3. [Implementation Plan](#implementation-plan)
4. [Event-Driven Architecture](#event-driven-architecture)
5. [API Gateway Setup](#api-gateway-setup)

---

## Overview

### What is a Bounded Context?

**Definition**: A bounded context is a logical boundary within which a particular domain model is defined and applicable.

**Key Concepts**:
- Each context has its own **ubiquitous language**
- Models can have different meanings in different contexts
- Contexts communicate through well-defined interfaces
- Each context can become a microservice

### Why Bounded Contexts?

**Current Problem**:
```
marketplace/
├── models.py          # Product, Order, Cart, Category, Review...
├── views.py           # All CRUD for all models
└── serializers.py     # All serializers
```

**Issues**:
- Unclear ownership
- Hard to find related code
- Cannot deploy contexts independently
- Tight coupling

**Target Structure**:
```
marketplace/
├── catalog/           # Product browsing context
│   ├── domain/
│   ├── api/
│   └── events/
├── cart/              # Shopping cart context
│   ├── domain/
│   ├── api/
│   └── events/
└── orders/            # Order management context
    ├── domain/
    ├── api/
    └── events/
```

---

## Bounded Context Strategy

### Identified Contexts

#### 1. Catalog Context

**Purpose**: Product browsing and discovery

**Responsibilities**:
- Product CRUD
- Category management
- Product search
- Product reviews
- Product favorites

**Models**:
- Product
- Category
- ProductImage
- ProductReview
- ProductFavorite

**Events Produced**:
- `product.created`
- `product.updated`
- `product.deleted`
- `product.out_of_stock`

**Events Consumed**:
- `order.completed` (update sales count)
- `inventory.stock_changed`

---

#### 2. Cart Context

**Purpose**: Shopping cart management

**Responsibilities**:
- Add/remove items
- Update quantities
- Cart persistence
- Price calculations

**Models**:
- Cart
- CartItem

**Events Produced**:
- `cart.item_added`
- `cart.item_removed`
- `cart.cleared`

**Events Consumed**:
- `product.price_changed`
- `product.deleted` (remove from carts)

---

#### 3. Orders Context

**Purpose**: Order lifecycle management

**Responsibilities**:
- Order creation
- Order status tracking
- Shipping management
- Order cancellation

**Models**:
- Order
- OrderItem
- OrderShipping

**Events Produced**:
- `order.created`
- `order.payment_initiated`
- `order.confirmed`
- `order.shipped`
- `order.delivered`
- `order.cancelled`

**Events Consumed**:
- `payment.succeeded`
- `payment.failed`
- `inventory.reserved`

---

#### 4. Payment Context

**Purpose**: Payment processing

**Responsibilities**:
- Checkout session creation
- Webhook handling
- Refund processing
- Payment tracking

**Models**:
- PaymentTracker
- PaymentTransaction
- Payout
- PayoutItem

**Events Produced**:
- `payment.initiated`
- `payment.succeeded`
- `payment.failed`
- `refund.initiated`
- `refund.completed`

**Events Consumed**:
- `order.created`
- `order.cancelled`

---

#### 5. Inventory Context

**Purpose**: Stock management

**Responsibilities**:
- Stock tracking
- Stock reservation
- Stock replenishment

**Models**:
- ProductMetrics (stock-related fields)

**Events Produced**:
- `inventory.reserved`
- `inventory.released`
- `inventory.depleted`

**Events Consumed**:
- `order.created` (reserve stock)
- `order.cancelled` (release stock)

---

#### 6. Identity Context

**Purpose**: User management and authentication

**Responsibilities**:
- User registration
- Authentication
- Profile management
- Seller verification

**Models**:
- CustomUser
- OAuthConnection
- TwoFactorAuth

**Events Produced**:
- `user.registered`
- `user.verified`
- `seller.approved`

---

### Context Map

```
┌─────────────────────────────────────────────────────┐
│                   API Gateway                        │
│  (Authentication, Rate Limiting, Routing)            │
└─────────────────────────────────────────────────────┘
         │
         ├───────────────┬───────────────┬───────────────┐
         │               │               │               │
         ▼               ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Catalog   │  │    Cart     │  │   Orders    │  │   Payment   │
│   Context   │  │   Context   │  │   Context   │  │   Context   │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
       │               │               │               │
       │               │               │               │
       └───────────────┴───────────────┴───────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Event Bus       │
              │  (Redis Pub/Sub) │
              └─────────────────┘
```

**Relationships**:
- **Catalog → Inventory**: Partnership (shared stock data)
- **Cart → Catalog**: Customer/Supplier (cart consumes product data)
- **Orders → Payment**: Partnership (order lifecycle)
- **Orders → Inventory**: Customer/Supplier (stock reservation)

---

## Implementation Plan

### Month 4: Context Reorganization

#### Week 1-2: Create Context Structure

**Goal**: Reorganize marketplace app by bounded contexts

**Steps**:

1. **Create Context Directories**
   ```bash
   cd marketplace
   mkdir -p catalog/domain catalog/api catalog/events catalog/tests
   mkdir -p cart/domain cart/api cart/events cart/tests
   mkdir -p orders/domain orders/api orders/events orders/tests
   ```

2. **Move Models**
   ```bash
   # Catalog context
   # Extract from models.py:
   - Product
   - Category
   - ProductImage
   - ProductReview
   - ProductFavorite
   # → catalog/domain/models.py

   # Cart context
   # Extract from models.py:
   - Cart
   - CartItem
   # → cart/domain/models.py

   # Orders context
   # Extract from models.py:
   - Order
   - OrderItem
   - OrderShipping
   # → orders/domain/models.py
   ```

3. **Update Imports**
   ```python
   # Before
   from marketplace.models import Product, Order

   # After
   from marketplace.catalog.domain.models import Product
   from marketplace.orders.domain.models import Order
   ```

4. **Move Services**
   ```bash
   # marketplace/services/catalog_service.py
   # → marketplace/catalog/domain/services.py

   # marketplace/services/cart_service.py
   # → marketplace/cart/domain/services.py

   # marketplace/services/order_service.py
   # → marketplace/orders/domain/services.py
   ```

5. **Move API Layer**
   ```bash
   # Create context-specific API modules
   marketplace/catalog/api/
   ├── views.py (ProductViewSet, CategoryViewSet)
   ├── serializers.py (Product serializers)
   └── urls.py (catalog routes)

   marketplace/cart/api/
   ├── views.py (CartViewSet)
   ├── serializers.py (Cart serializers)
   └── urls.py (cart routes)

   marketplace/orders/api/
   ├── views.py (OrderViewSet)
   ├── serializers.py (Order serializers)
   └── urls.py (order routes)
   ```

**Deliverables**:
- Reorganized marketplace app
- All imports updated
- All tests passing
- No functionality changes

---

#### Week 3-4: Decouple Cross-Context Dependencies

**Goal**: Remove foreign keys between contexts

**Current Problem**:
```python
# orders/models.py
class Order(models.Model):
    buyer = models.ForeignKey(User, ...)  # Cross-context FK
    # Cannot split to separate databases

# cart/models.py
class CartItem(models.Model):
    product = models.ForeignKey(Product, ...)  # Cross-context FK
```

**Solution**: Replace with IDs + Event-driven queries

**Step 1: Replace Foreign Keys**

```python
# Before (orders/domain/models.py)
class Order(models.Model):
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    # Tight coupling to identity context

# After
class Order(models.Model):
    buyer_id = models.UUIDField()  # Just store ID
    buyer_email = models.EmailField()  # Denormalize critical data
    buyer_name = models.CharField(max_length=200)

    # No FK = can use separate database
```

**Step 2: Create Context Service for Queries**

```python
# orders/domain/services.py
class OrderService:
    def __init__(self, identity_service: IdentityServiceInterface):
        self.identity_service = identity_service

    def get_order_with_buyer(self, order_id: UUID):
        """Get order with buyer details"""
        order = Order.objects.get(id=order_id)

        # Fetch buyer from identity context via API/event
        buyer = self.identity_service.get_user(order.buyer_id)

        return {
            'order': order,
            'buyer': buyer
        }
```

**Step 3: Create Identity Service Interface**

```python
# marketplace/common/interfaces.py
class IdentityServiceInterface(ABC):
    @abstractmethod
    def get_user(self, user_id: UUID) -> dict:
        """Get user by ID"""
        pass

    @abstractmethod
    def verify_user_exists(self, user_id: UUID) -> bool:
        """Check if user exists"""
        pass


# marketplace/common/identity_service.py
class IdentityService(IdentityServiceInterface):
    """Local implementation - calls authentication app"""

    def get_user(self, user_id: UUID) -> dict:
        from authentication.models import CustomUser

        try:
            user = CustomUser.objects.get(id=user_id)
            return {
                'id': user.id,
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}",
                'role': user.role
            }
        except CustomUser.DoesNotExist:
            return None


# Future: When split to microservices
class IdentityServiceHTTP(IdentityServiceInterface):
    """HTTP implementation - calls identity microservice"""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_user(self, user_id: UUID) -> dict:
        response = requests.get(f"{self.base_url}/users/{user_id}")
        if response.status_code == 200:
            return response.json()
        return None
```

**Migration Steps**:

1. **Add new ID fields** (don't remove FK yet)
   ```python
   class Order(models.Model):
       buyer = models.ForeignKey(User, ...)  # Keep for now
       buyer_id_new = models.UUIDField(null=True)  # New field
       buyer_email = models.EmailField(null=True)  # Denormalized
   ```

2. **Backfill data**
   ```python
   # Data migration
   for order in Order.objects.all():
       order.buyer_id_new = order.buyer.id
       order.buyer_email = order.buyer.email
       order.save()
   ```

3. **Update code to use new fields**
   ```python
   # Use buyer_id_new instead of buyer FK
   ```

4. **Remove FK** (after verification)
   ```python
   class Order(models.Model):
       # buyer = models.ForeignKey... (REMOVED)
       buyer_id = models.UUIDField()  # Renamed from buyer_id_new
       buyer_email = models.EmailField()
   ```

**Deliverables**:
- No cross-context foreign keys
- Identity service interface
- Data migration completed
- All tests passing

---

### Month 5: Event-Driven Architecture

#### Week 5-6: Event System Implementation

**Goal**: Implement event publishing and subscription

**Architecture**:
```
Context A                        Event Bus                    Context B
    │                               │                             │
    ├─ Publish Event ──────────────▶│                             │
    │  (order.created)               │                             │
    │                               ├─ Route Event ───────────────▶│
    │                               │                             ├─ Handle Event
    │                               │                             │  (reserve_stock)
    │                               │◀─ Confirm ──────────────────┤
```

**Technology**: Redis Pub/Sub (already have Redis for Celery)

**Step 1: Create Event Framework**

```python
# marketplace/common/events/event.py
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict
import uuid

@dataclass
class DomainEvent:
    """Base class for all domain events"""
    event_id: str
    event_type: str
    occurred_at: datetime
    payload: Dict[str, Any]
    aggregate_id: str

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.occurred_at:
            self.occurred_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return asdict(self)


# marketplace/common/events/bus.py
import redis
import json
from typing import Callable, List

class EventBus:
    """Redis-based event bus"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.handlers: Dict[str, List[Callable]] = {}

    def publish(self, event: DomainEvent):
        """Publish event to Redis"""
        channel = f"events.{event.event_type}"
        message = json.dumps(event.to_dict(), default=str)

        self.redis.publish(channel, message)
        logger.info(f"Published event: {event.event_type} ({event.event_id})")

    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to event type"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []

        self.handlers[event_type].append(handler)

    def start_listening(self):
        """Start listening for events (run in Celery worker)"""
        pubsub = self.redis.pubsub()

        # Subscribe to all event channels
        for event_type in self.handlers.keys():
            pubsub.subscribe(f"events.{event_type}")

        logger.info(f"Listening for events: {list(self.handlers.keys())}")

        for message in pubsub.listen():
            if message['type'] == 'message':
                self._handle_message(message)

    def _handle_message(self, message):
        """Handle incoming event"""
        try:
            event_data = json.loads(message['data'])
            event_type = event_data['event_type']

            handlers = self.handlers.get(event_type, [])
            for handler in handlers:
                try:
                    handler(event_data)
                except Exception as e:
                    logger.exception(f"Event handler failed: {e}")
        except Exception as e:
            logger.exception(f"Failed to process event: {e}")
```

**Step 2: Define Context Events**

```python
# marketplace/orders/events/events.py
@dataclass
class OrderCreatedEvent(DomainEvent):
    """Event published when order is created"""

    def __init__(self, order: Order):
        super().__init__(
            event_id=None,
            event_type="order.created",
            occurred_at=None,
            aggregate_id=str(order.id),
            payload={
                'order_id': str(order.id),
                'buyer_id': str(order.buyer_id),
                'total_amount': float(order.total_amount),
                'items': [
                    {
                        'product_id': str(item.product_id),
                        'quantity': item.quantity,
                        'price': float(item.unit_price)
                    }
                    for item in order.items.all()
                ]
            }
        )


@dataclass
class OrderConfirmedEvent(DomainEvent):
    """Event published when payment succeeds"""

    def __init__(self, order: Order):
        super().__init__(
            event_id=None,
            event_type="order.confirmed",
            occurred_at=None,
            aggregate_id=str(order.id),
            payload={
                'order_id': str(order.id),
                'buyer_id': str(order.buyer_id),
            }
        )
```

**Step 3: Publish Events from Services**

```python
# marketplace/orders/domain/services.py
class OrderService:
    def __init__(self, event_bus: EventBus, inventory_service, payment_service):
        self.event_bus = event_bus
        self.inventory_service = inventory_service
        self.payment_service = payment_service

    def create_order(self, buyer_id: UUID, cart_items: List[CartItem]) -> ServiceResult[Order]:
        """Create order and publish event"""

        with transaction.atomic():
            # 1. Create order
            order = Order.objects.create(
                buyer_id=buyer_id,
                status='pending_payment',
                # ... other fields
            )

            # 2. Create order items
            for cart_item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product_id=cart_item.product_id,
                    quantity=cart_item.quantity,
                    # ...
                )

            # 3. Publish event
            event = OrderCreatedEvent(order)
            self.event_bus.publish(event)

            return service_ok(order)
```

**Step 4: Subscribe to Events**

```python
# marketplace/catalog/events/handlers.py
class CatalogEventHandler:
    """Handle events for catalog context"""

    def __init__(self, catalog_service: CatalogService):
        self.catalog_service = catalog_service

    def handle_order_completed(self, event_data: dict):
        """Update product sales count when order completes"""
        order_id = event_data['payload']['order_id']
        items = event_data['payload']['items']

        for item in items:
            product_id = item['product_id']
            quantity = item['quantity']

            # Update sales count
            Product.objects.filter(id=product_id).update(
                sales_count=models.F('sales_count') + quantity
            )

        logger.info(f"Updated sales counts for order {order_id}")


# marketplace/catalog/apps.py
from django.apps import AppConfig

class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marketplace.catalog'

    def ready(self):
        from marketplace.common.events.bus import get_event_bus
        from .events.handlers import CatalogEventHandler

        event_bus = get_event_bus()
        handler = CatalogEventHandler(catalog_service)

        # Subscribe to events
        event_bus.subscribe('order.completed', handler.handle_order_completed)
```

**Step 5: Event Worker (Celery)**

```python
# designiaBackend/celery.py
@app.task
def event_listener_task():
    """Celery task to listen for events"""
    from marketplace.common.events.bus import get_event_bus

    event_bus = get_event_bus()
    event_bus.start_listening()  # Blocking call
```

Start worker:
```bash
celery -A designiaBackend worker -Q events --loglevel=info
```

**Deliverables**:
- Event bus implemented
- 5+ events defined
- Event handlers for each context
- Event worker running
- Documentation

---

#### Week 7-8: Saga Pattern for Distributed Transactions

**Goal**: Implement saga pattern for order creation

**Problem**: Order creation requires coordinating multiple contexts:
1. Create order (Orders context)
2. Reserve stock (Inventory context)
3. Process payment (Payment context)
4. Send confirmation (Notification context)

**Solution**: Saga orchestrator

```python
# marketplace/orders/sagas/order_creation_saga.py
from enum import Enum

class SagaStep(Enum):
    ORDER_CREATED = "order_created"
    STOCK_RESERVED = "stock_reserved"
    PAYMENT_PROCESSED = "payment_processed"
    CONFIRMATION_SENT = "confirmation_sent"


class OrderCreationSaga:
    """Orchestrates order creation across multiple contexts"""

    def __init__(
        self,
        order_service: OrderService,
        inventory_service: InventoryService,
        payment_service: PaymentService,
        notification_service: NotificationService,
    ):
        self.order_service = order_service
        self.inventory_service = inventory_service
        self.payment_service = payment_service
        self.notification_service = notification_service

    async def execute(
        self,
        buyer_id: UUID,
        cart_items: List[CartItem]
    ) -> ServiceResult[Order]:
        """Execute saga"""

        compensation_stack = []
        order = None

        try:
            # Step 1: Create order
            order_result = self.order_service.create_order(buyer_id, cart_items)
            if not order_result.ok:
                return order_result

            order = order_result.value
            compensation_stack.append(
                lambda: self.order_service.cancel_order(order.id)
            )

            # Step 2: Reserve stock
            for item in cart_items:
                reserve_result = self.inventory_service.reserve_stock(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    order_id=order.id
                )

                if not reserve_result.ok:
                    # Compensate: rollback
                    await self._compensate(compensation_stack)
                    return service_err(
                        "stock_reservation_failed",
                        reserve_result.detail
                    )

                compensation_stack.append(
                    lambda: self.inventory_service.release_stock(
                        product_id=item.product_id,
                        quantity=item.quantity,
                        order_id=order.id
                    )
                )

            # Step 3: Process payment
            payment_result = self.payment_service.create_checkout_session(order)
            if not payment_result.ok:
                await self._compensate(compensation_stack)
                return service_err("payment_failed", payment_result.detail)

            # Step 4: Send confirmation
            self.notification_service.send_order_confirmation(order)

            return service_ok(order)

        except Exception as e:
            logger.exception(f"Saga failed: {e}")
            if compensation_stack:
                await self._compensate(compensation_stack)
            return service_err("saga_failed", str(e))

    async def _compensate(self, compensation_stack: List[Callable]):
        """Execute compensation actions in reverse order"""
        logger.warning("Executing saga compensation")

        for compensate in reversed(compensation_stack):
            try:
                compensate()
            except Exception as e:
                logger.exception(f"Compensation failed: {e}")
```

**Usage**:

```python
# orders/api/views.py
class OrderViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    async def create_from_cart(self, request):
        """Create order from cart using saga"""

        saga = OrderCreationSaga(
            order_service=container.order_service(),
            inventory_service=container.inventory_service(),
            payment_service=container.payment_service(),
            notification_service=container.notification_service(),
        )

        result = await saga.execute(
            buyer_id=request.user.id,
            cart_items=request.user.cart.items.all()
        )

        if not result.ok:
            return Response(
                {"error": result.error, "detail": result.detail},
                status=400
            )

        return Response(
            OrderSerializer(result.value).data,
            status=201
        )
```

**Deliverables**:
- Saga pattern implemented
- Compensation logic tested
- Distributed transaction working
- Failure scenarios handled

---

### Month 6: API Gateway & Observability

#### Week 9-10: API Gateway Setup

**Goal**: Centralize cross-cutting concerns

**Technology**: Kong API Gateway

**Architecture**:
```
Client
  │
  ▼
┌─────────────────────────────────┐
│      Kong API Gateway           │
│  - Authentication (JWT)         │
│  - Rate Limiting                │
│  - CORS                         │
│  - Request/Response Transform   │
│  - Logging                      │
└─────────────────────────────────┘
  │
  ├────────────┬────────────┬─────────────┐
  ▼            ▼            ▼             ▼
Catalog      Cart        Orders       Payment
Service     Service     Service       Service
```

**Installation**:

```bash
# Docker Compose
docker-compose.yml:

version: '3.8'
services:
  kong-database:
    image: postgres:13
    environment:
      POSTGRES_DB: kong
      POSTGRES_USER: kong
      POSTGRES_PASSWORD: kong

  kong-migrations:
    image: kong:3.0
    command: kong migrations bootstrap
    depends_on:
      - kong-database

  kong:
    image: kong:3.0
    depends_on:
      - kong-database
    environment:
      KONG_DATABASE: postgres
      KONG_PG_HOST: kong-database
      KONG_PG_USER: kong
      KONG_PG_PASSWORD: kong
      KONG_PROXY_ACCESS_LOG: /dev/stdout
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
      KONG_ADMIN_LISTEN: 0.0.0.0:8001
    ports:
      - "8000:8000"  # Proxy
      - "8001:8001"  # Admin API
```

**Configuration**:

```bash
# Add services to Kong

# 1. Catalog service
curl -X POST http://localhost:8001/services \
  --data name=catalog-service \
  --data url=http://backend:8000/api/catalog

# 2. Add route
curl -X POST http://localhost:8001/services/catalog-service/routes \
  --data paths[]=/api/products \
  --data paths[]=/api/categories

# 3. Add JWT authentication
curl -X POST http://localhost:8001/services/catalog-service/plugins \
  --data name=jwt

# 4. Add rate limiting
curl -X POST http://localhost:8001/services/catalog-service/plugins \
  --data name=rate-limiting \
  --data config.minute=100 \
  --data config.policy=local

# 5. Add CORS
curl -X POST http://localhost:8001/services/catalog-service/plugins \
  --data name=cors \
  --data config.origins=http://localhost:3000
```

**Deliverables**:
- Kong API Gateway running
- All routes configured
- JWT authentication enabled
- Rate limiting active
- Documentation

---

#### Week 11-12: Distributed Tracing

**Goal**: Track requests across contexts

**Technology**: OpenTelemetry + Jaeger

**Setup**:

```python
# utils/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def setup_tracing():
    """Setup distributed tracing"""

    # Create tracer provider
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)

    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )

    # Add span processor
    tracer_provider.add_span_processor(
        BatchSpanProcessor(jaeger_exporter)
    )

    # Instrument Django
    DjangoInstrumentor().instrument()

    # Instrument HTTP requests
    RequestsInstrumentor().instrument()


# settings.py
if not DEBUG:
    setup_tracing()
```

**Usage**:

```python
# orders/domain/services.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class OrderService:
    @tracer.start_as_current_span("create_order")
    def create_order(self, buyer_id, cart_items):
        """Create order with tracing"""

        with tracer.start_as_current_span("validate_cart"):
            # Validation logic

        with tracer.start_as_current_span("reserve_inventory"):
            # Reserve stock

        with tracer.start_as_current_span("create_payment"):
            # Payment processing

        return order
```

**Deliverables**:
- Distributed tracing implemented
- Jaeger dashboard accessible
- All contexts instrumented
- Performance insights

---

## Success Criteria

### Technical Metrics

- [ ] **Bounded Contexts**: 6 contexts defined and implemented
- [ ] **Cross-Context FKs**: 0 (all removed)
- [ ] **Event Coverage**: 15+ events defined
- [ ] **Saga Patterns**: 2+ sagas implemented
- [ ] **API Gateway**: All routes through gateway
- [ ] **Distributed Tracing**: 100% request coverage

### Quality Metrics

- [ ] **Context Cohesion**: 80%+ related code in same context
- [ ] **Context Coupling**: Low (< 3 dependencies per context)
- [ ] **Event Delivery**: 99.9%+ success rate
- [ ] **Tracing Overhead**: < 5% latency increase

---

## Next Phase

Upon completion of Phase 2, evaluate:
- [PHASE3_MICROSERVICES_EXTRACTION.md](./PHASE3_MICROSERVICES_EXTRACTION.md)

---

**Document Status**: Complete
**Last Updated**: 2025-11-29
