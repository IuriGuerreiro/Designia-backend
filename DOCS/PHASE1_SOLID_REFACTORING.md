# Phase 1: SOLID Refactoring Implementation Guide

**Phase Duration**: 3 months
**Goal**: Apply SOLID principles to achieve 80+ SOLID score
**Status**: Planning

## Table of Contents

1. [Overview](#overview)
2. [Week-by-Week Plan](#week-by-week-plan)
3. [Implementation Steps](#implementation-steps)
4. [Testing Strategy](#testing-strategy)
5. [Success Criteria](#success-criteria)

---

## Overview

### Objectives

- ✅ Extract all business logic into service layer
- ✅ Implement dependency inversion for infrastructure
- ✅ Decompose fat models into domain services
- ✅ Create segregated interfaces (serializers)
- ✅ Achieve 80%+ test coverage

### Scope

**In Scope**:
- marketplace app (full refactoring)
- payment_system app (full refactoring)
- authentication/services (complete service layer)
- Infrastructure abstractions (storage, email, payments)

**Out of Scope**:
- activity, chat, ar apps (Phase 2)
- Database schema changes
- Microservices extraction
- Frontend changes

### Team Requirements

- **Backend Developer**: 1 full-time
- **QA Engineer**: 0.5 time (testing support)
- **Code Reviewers**: 2 developers (peer review)

---

## Week-by-Week Plan

### Month 1: Foundation & Infrastructure

#### Week 1-2: Setup & Infrastructure Abstractions

**Goal**: Create abstraction layer for external dependencies

**Tasks**:

1. **Create infrastructure package structure**
   ```bash
   mkdir -p infrastructure/storage
   mkdir -p infrastructure/email
   mkdir -p infrastructure/payments
   mkdir -p infrastructure/notifications
   ```

2. **Implement Storage Abstraction**
   - [ ] Create `StorageInterface` (abstract base class)
   - [ ] Implement `S3StorageAdapter`
   - [ ] Implement `LocalStorageAdapter`
   - [ ] Create `StorageFactory`
   - [ ] Write unit tests (80% coverage)

3. **Implement Email Abstraction**
   - [ ] Create `EmailServiceInterface`
   - [ ] Implement `SMTPEmailService`
   - [ ] Implement `MockEmailService` (testing)
   - [ ] Create `EmailFactory`

4. **Setup Dependency Injection**
   - [ ] Install `dependency-injector`
   - [ ] Create `Container` class
   - [ ] Configure services in container

**Deliverables**:
- `infrastructure/` package with 4 adapters
- 20+ unit tests
- Configuration guide

**Files to Create**:
```
infrastructure/
├── __init__.py
├── storage/
│   ├── __init__.py
│   ├── interface.py
│   ├── s3_adapter.py
│   ├── local_adapter.py
│   └── factory.py
├── email/
│   ├── __init__.py
│   ├── interface.py
│   ├── smtp_service.py
│   └── mock_service.py
└── payments/
    ├── __init__.py
    ├── interface.py
    ├── stripe_provider.py
    └── factory.py
```

---

#### Week 3-4: Service Layer Foundation

**Goal**: Establish service layer pattern for marketplace

**Tasks**:

1. **Create Service Base Classes**
   ```python
   # utils/service_base.py (already exists, enhance)
   - Add logging decorator
   - Add performance monitoring
   - Add error handling wrapper
   ```

2. **Create Marketplace Services**
   - [ ] `CatalogService` (product browsing)
   - [ ] `CartService` (shopping cart)
   - [ ] `OrderService` (order management)
   - [ ] `InventoryService` (stock management)
   - [ ] `PricingService` (price calculations)

3. **Migrate First View to Service**
   - [ ] Choose simple view (e.g., ProductListView)
   - [ ] Extract logic to service
   - [ ] Update view to call service
   - [ ] Write integration tests
   - [ ] Deploy and monitor

**Example Migration**:

**Before** (`marketplace/views.py`):
```python
class ProductViewSet(viewsets.ModelViewSet):
    def list(self, request):
        # 50+ lines of business logic
        products = Product.objects.filter(is_active=True)
        # Complex filtering
        # Pagination
        # Tracking
        # Response formatting
```

**After** (`marketplace/api/views.py`):
```python
class ProductViewSet(viewsets.ModelViewSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.catalog_service = CatalogService(
            storage=container.storage(),
            tracking=container.tracking_service()
        )

    def list(self, request):
        # Thin controller - 5 lines
        result = self.catalog_service.list_products(
            filters=request.query_params,
            user=request.user
        )

        if not result.ok:
            return Response({"error": result.error}, status=400)

        serializer = ProductListSerializer(result.value, many=True)
        return Response(serializer.data)
```

**Deliverables**:
- 5 service classes with full implementation
- 1 refactored viewset
- 30+ service tests
- Performance baseline

---

### Month 2: Core Refactoring

#### Week 5-6: Marketplace Views → Services

**Goal**: Migrate all marketplace views to service layer

**Priority Order** (migrate in this sequence):

1. **ProductViewSet** (highest complexity)
   - [ ] `list()` → `CatalogService.list_products()`
   - [ ] `retrieve()` → `CatalogService.get_product_detail()`
   - [ ] `create()` → `CatalogService.create_product()`
   - [ ] `update()` → `CatalogService.update_product()`
   - [ ] `upload_images()` → `CatalogService.upload_product_images()`

2. **CartViewSet**
   - [ ] `add_item()` → `CartService.add_to_cart()`
   - [ ] `remove_item()` → `CartService.remove_from_cart()`
   - [ ] `update_quantity()` → `CartService.update_quantity()`
   - [ ] `clear()` → `CartService.clear_cart()`

3. **OrderViewSet**
   - [ ] `create_order()` → `OrderService.create_order()`
   - [ ] `cancel_order()` → `OrderService.cancel_order()`
   - [ ] `update_shipping()` → `OrderService.update_shipping()`

**Daily Workflow**:

1. **Morning** (2 hours):
   - Pick one view method
   - Extract to service
   - Write tests

2. **Afternoon** (2 hours):
   - Update view to call service
   - Run full test suite
   - Performance check
   - Code review

3. **Evening** (1 hour):
   - Deploy to staging
   - Monitor for issues
   - Document changes

**Deliverables**:
- All marketplace views refactored
- Views < 500 LOC each
- 60+ integration tests
- Performance report

---

#### Week 7-8: Payment System Refactoring

**Goal**: Implement payment provider abstraction

**Tasks**:

1. **Create Payment Provider Interface**
   - [ ] Define `PaymentProvider` abstract class
   - [ ] Define `CheckoutSession` dataclass
   - [ ] Define `WebhookEvent` dataclass

2. **Implement Stripe Provider**
   - [ ] `StripeProvider` class
   - [ ] Migrate `create_checkout_session()`
   - [ ] Migrate `verify_webhook()`
   - [ ] Migrate `handle_webhook_event()`
   - [ ] Extract event handlers to separate methods

3. **Refactor Payment Views**
   - [ ] Inject payment provider
   - [ ] Update `create_checkout_session` view
   - [ ] Update `stripe_webhook` view
   - [ ] Add provider factory

4. **Testing**
   - [ ] Mock payment provider tests
   - [ ] Stripe integration tests
   - [ ] Webhook signature verification tests

**Critical**: Payment system has most technical debt (3,443 LOC)
- Break into smaller chunks
- Test extensively
- Feature flag new implementation
- Run parallel for 1 week

**Deliverables**:
- Payment provider abstraction
- Refactored payment views
- 40+ payment tests
- Rollback plan documented

---

### Month 3: Domain Services & Testing

#### Week 9-10: Model Decomposition

**Goal**: Extract business logic from models

**Current Problem**:
```python
class Product(models.Model):
    # 25+ methods mixing data and business logic
    def is_on_sale(self): ...
    def average_rating(self): ...
    def discount_percentage(self): ...
```

**Target Structure**:
```
marketplace/domain/
├── models.py (data only)
├── pricing.py (PricingService)
├── inventory.py (InventoryService)
├── reviews.py (ReviewMetricsService)
└── search.py (SearchService)
```

**Migration Strategy**:

1. **Create Domain Services** (Day 1-3)
   ```python
   # marketplace/domain/pricing.py
   class PricingService:
       @staticmethod
       def is_on_sale(product: Product) -> bool:
           return (
               product.original_price
               and product.original_price > product.price
           )

       @staticmethod
       def calculate_discount(product: Product) -> int:
           if not PricingService.is_on_sale(product):
               return 0
           discount = product.original_price - product.price
           return int((discount / product.original_price) * 100)
   ```

2. **Add Deprecation Warnings** (Day 4-5)
   ```python
   class Product(models.Model):
       @property
       def is_on_sale(self):
           import warnings
           warnings.warn(
               "Product.is_on_sale is deprecated. Use PricingService.is_on_sale()",
               DeprecationWarning
           )
           return PricingService.is_on_sale(self)
   ```

3. **Update Callers** (Day 6-8)
   - Find all uses: `grep -r "\.is_on_sale" .`
   - Replace with service calls
   - Run tests after each file

4. **Remove Model Methods** (Day 9-10)
   - Remove deprecated methods
   - Final testing
   - Deploy

**Deliverables**:
- 5 domain services created
- All model business logic extracted
- 0 deprecation warnings
- Models < 100 LOC

---

#### Week 11-12: Interface Segregation & Testing

**Goal**: Segregate serializers and achieve 80% coverage

**Tasks**:

1. **Serializer Refactoring**

   **Before** (1 fat serializer):
   ```python
   class ProductSerializer(serializers.ModelSerializer):
       # 25 fields
       # 5 method fields
       # Used for list, detail, create, update
   ```

   **After** (4 segregated serializers):
   ```python
   ProductListSerializer         # 7 fields
   ProductDetailSerializer       # 20 fields
   ProductCreateSerializer       # 10 fields
   ProductSearchResultSerializer # 5 fields + score
   ```

   - [ ] Create `ProductListSerializer`
   - [ ] Create `ProductDetailSerializer`
   - [ ] Create `ProductCreateSerializer`
   - [ ] Update views to use appropriate serializer
   - [ ] Measure performance improvement

2. **Comprehensive Testing**

   **Test Coverage Goals**:
   - Services: 90%+
   - Views: 80%+
   - Models: 70%+
   - Utils: 85%+
   - **Overall**: 80%+

   **Test Types**:
   ```
   tests/
   ├── unit/
   │   ├── test_services/
   │   │   ├── test_catalog_service.py
   │   │   ├── test_cart_service.py
   │   │   └── test_order_service.py
   │   └── test_domain/
   │       ├── test_pricing.py
   │       └── test_inventory.py
   ├── integration/
   │   ├── test_product_api.py
   │   ├── test_cart_api.py
   │   └── test_order_api.py
   └── performance/
       └── test_benchmarks.py
   ```

3. **Performance Testing**
   - [ ] Benchmark product list (before/after)
   - [ ] Benchmark product detail (before/after)
   - [ ] Benchmark cart operations
   - [ ] Database query count analysis

**Deliverables**:
- Segregated serializers (12+ new serializers)
- 200+ tests written
- 80%+ coverage achieved
- Performance improved or maintained

---

## Implementation Steps

### Step-by-Step: Migrating a View to Service

Let's walk through migrating `ProductViewSet.create()`:

#### Step 1: Analyze Current Code

```python
# marketplace/views.py
class ProductViewSet(viewsets.ModelViewSet):
    def create(self, request):
        # 1. Validation (serializer)
        serializer = ProductCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. Business logic
        with transaction.atomic():
            product = Product.objects.create(
                seller=request.user,
                **serializer.validated_data
            )

            # 3. Image processing
            images = request.FILES.getlist('images')
            for idx, image_file in enumerate(images):
                validated_image = validate_and_process_image(image_file)

                # 4. S3 upload
                s3_storage = get_s3_storage()
                result = s3_storage.upload_file(
                    validated_image['file'],
                    f"products/{product.id}/{validated_image['random_name']}"
                )

                # 5. Database record
                ProductImage.objects.create(
                    product=product,
                    s3_key=result['key'],
                    s3_bucket=result['bucket'],
                    is_primary=(idx == 0)
                )

            # 6. Metrics initialization
            ProductMetrics.objects.create(product=product)

            # 7. Activity tracking
            UserClick.objects.create(
                user=request.user,
                action='product_created',
                product=product
            )

        # 8. Response
        return Response(
            ProductDetailSerializer(product).data,
            status=status.HTTP_201_CREATED
        )
```

**Complexity**: ~50 lines, 8 responsibilities

#### Step 2: Create Service

```python
# marketplace/services/catalog_service.py
from typing import List, BinaryIO
from dataclasses import dataclass

@dataclass
class CreateProductData:
    name: str
    description: str
    price: Decimal
    category_id: int
    stock_quantity: int
    images: List[BinaryIO]


class CatalogService:
    """Handles product catalog operations"""

    def __init__(
        self,
        storage: StorageInterface,
        image_processor: ImageProcessingService,
        tracking_service: TrackingService,
    ):
        self.storage = storage
        self.image_processor = image_processor
        self.tracking = tracking_service

    def create_product(
        self,
        user: User,
        data: CreateProductData
    ) -> ServiceResult[Product]:
        """Create product with images and initialize metrics"""

        try:
            with transaction.atomic():
                # 1. Create product
                product = Product.objects.create(
                    seller=user,
                    name=data.name,
                    description=data.description,
                    price=data.price,
                    category_id=data.category_id,
                    stock_quantity=data.stock_quantity,
                )

                # 2. Process and upload images
                upload_result = self._upload_product_images(product, data.images)
                if not upload_result.ok:
                    # Transaction will rollback
                    return upload_result

                # 3. Initialize metrics
                ProductMetrics.objects.create(product=product)

                # 4. Track activity
                self.tracking.track_product_created(user, product)

                return service_ok(product)

        except Exception as e:
            logger.exception(f"Failed to create product: {e}")
            return service_err("creation_failed", str(e))

    def _upload_product_images(
        self,
        product: Product,
        images: List[BinaryIO]
    ) -> ServiceResult[List[ProductImage]]:
        """Process and upload product images"""

        uploaded_images = []

        try:
            for idx, image_file in enumerate(images):
                # Process image (validation, resizing, etc.)
                processed = self.image_processor.process(image_file)

                # Upload to storage
                stored_file = self.storage.upload(
                    file=processed.file,
                    path=f"products/{product.id}/{processed.random_name}",
                    content_type=processed.content_type
                )

                # Create database record
                product_image = ProductImage.objects.create(
                    product=product,
                    s3_key=stored_file.key,
                    s3_bucket=self.storage.bucket_name,
                    file_size=stored_file.size,
                    content_type=stored_file.content_type,
                    is_primary=(idx == 0)
                )

                uploaded_images.append(product_image)

            return service_ok(uploaded_images)

        except Exception as e:
            # Cleanup uploaded files
            for image in uploaded_images:
                self.storage.delete(image.s3_key)

            logger.exception(f"Failed to upload images: {e}")
            return service_err("upload_failed", str(e))
```

#### Step 3: Update View

```python
# marketplace/api/views.py
class ProductViewSet(viewsets.ModelViewSet):
    """Thin controller - delegates to service layer"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dependency injection
        self.catalog_service = CatalogService(
            storage=container.storage(),
            image_processor=container.image_processor(),
            tracking_service=container.tracking_service(),
        )

    def create(self, request):
        """Create product - thin wrapper"""

        # 1. Input validation (serializer's job)
        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. Build service input
        create_data = CreateProductData(
            name=serializer.validated_data['name'],
            description=serializer.validated_data['description'],
            price=serializer.validated_data['price'],
            category_id=serializer.validated_data['category'],
            stock_quantity=serializer.validated_data['stock_quantity'],
            images=request.FILES.getlist('images')
        )

        # 3. Call service
        result = self.catalog_service.create_product(
            user=request.user,
            data=create_data
        )

        # 4. Handle result
        if not result.ok:
            return Response(
                {"error": result.error, "detail": result.detail},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Format response
        return Response(
            ProductDetailSerializer(result.value).data,
            status=status.HTTP_201_CREATED
        )
```

**Result**: View reduced from ~50 lines → 15 lines

#### Step 4: Write Tests

```python
# tests/unit/test_catalog_service.py
import pytest
from unittest.mock import Mock, MagicMock
from marketplace.services.catalog_service import CatalogService, CreateProductData

@pytest.fixture
def mock_storage():
    storage = Mock(spec=StorageInterface)
    storage.upload.return_value = Mock(
        key='products/123/image.jpg',
        url='https://example.com/image.jpg',
        size=1024,
        content_type='image/jpeg'
    )
    return storage

@pytest.fixture
def mock_image_processor():
    processor = Mock(spec=ImageProcessingService)
    processor.process.return_value = Mock(
        file=MagicMock(),
        random_name='abc123.jpg',
        content_type='image/jpeg'
    )
    return processor

@pytest.fixture
def catalog_service(mock_storage, mock_image_processor):
    return CatalogService(
        storage=mock_storage,
        image_processor=mock_image_processor,
        tracking_service=Mock()
    )

def test_create_product_success(catalog_service, user, mock_storage):
    """Test successful product creation"""

    data = CreateProductData(
        name="Test Product",
        description="Test description",
        price=Decimal("99.99"),
        category_id=1,
        stock_quantity=10,
        images=[Mock()]
    )

    result = catalog_service.create_product(user, data)

    assert result.ok
    assert result.value.name == "Test Product"
    assert result.value.price == Decimal("99.99")

    # Verify storage was called
    mock_storage.upload.assert_called_once()

def test_create_product_invalid_image(catalog_service, user, mock_image_processor):
    """Test product creation with invalid image"""

    # Mock image processor to fail
    mock_image_processor.process.side_effect = ValidationError("Invalid image")

    data = CreateProductData(
        name="Test Product",
        description="Test",
        price=Decimal("99.99"),
        category_id=1,
        stock_quantity=10,
        images=[Mock()]
    )

    result = catalog_service.create_product(user, data)

    assert not result.ok
    assert result.error == "upload_failed"

def test_create_product_storage_failure(catalog_service, user, mock_storage):
    """Test product creation when storage fails"""

    # Mock storage to fail
    mock_storage.upload.side_effect = Exception("S3 error")

    data = CreateProductData(
        name="Test Product",
        description="Test",
        price=Decimal("99.99"),
        category_id=1,
        stock_quantity=10,
        images=[Mock()]
    )

    result = catalog_service.create_product(user, data)

    assert not result.ok
    assert "upload_failed" in result.error
```

```python
# tests/integration/test_product_api.py
import pytest
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
def test_create_product_api(api_client, authenticated_user, category):
    """Integration test for product creation endpoint"""

    # Prepare test image
    image = SimpleUploadedFile(
        "test.jpg",
        b"fake image content",
        content_type="image/jpeg"
    )

    data = {
        'name': 'Test Product',
        'description': 'Test description',
        'price': '99.99',
        'category': category.id,
        'stock_quantity': 10,
        'images': [image]
    }

    response = api_client.post('/api/products/', data, format='multipart')

    assert response.status_code == 201
    assert response.data['name'] == 'Test Product'
    assert response.data['price'] == '99.99'
    assert len(response.data['images']) == 1
```

#### Step 5: Deploy & Monitor

```python
# Feature flag for gradual rollout
if settings.USE_NEW_PRODUCT_CREATION:
    result = self.catalog_service.create_product(...)
else:
    # Old implementation (fallback)
    result = old_create_product(...)
```

**Monitoring**:
- Response time: before vs after
- Error rate: track failures
- Database queries: N+1 detection
- S3 upload success rate

---

## Testing Strategy

### Test Pyramid

```
         /\
        /  \    E2E Tests (5%)
       /____\   - Critical user journeys
      /      \  Integration Tests (25%)
     /________\ - API endpoints
    /          \ Unit Tests (70%)
   /____________\ - Service layer, domain logic
```

### Coverage Requirements

| Layer | Coverage Target | Priority |
|-------|----------------|----------|
| Services | 90%+ | Critical |
| Domain Logic | 90%+ | Critical |
| Views | 80%+ | High |
| Models | 70%+ | Medium |
| Utils | 85%+ | High |
| **Overall** | **80%+** | **Required** |

### Testing Tools

```bash
# Install testing dependencies
pip install pytest pytest-django pytest-cov factory-boy faker

# Run tests with coverage
pytest --cov=marketplace --cov=payment_system --cov-report=html

# Check coverage
coverage report --fail-under=80
```

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── factories/               # Factory Boy factories
│   ├── user_factory.py
│   ├── product_factory.py
│   └── order_factory.py
├── unit/
│   ├── services/
│   │   ├── test_catalog_service.py
│   │   ├── test_cart_service.py
│   │   └── test_order_service.py
│   ├── domain/
│   │   ├── test_pricing.py
│   │   └── test_inventory.py
│   └── infrastructure/
│       ├── test_storage_adapter.py
│       └── test_email_service.py
├── integration/
│   ├── test_product_api.py
│   ├── test_cart_api.py
│   └── test_order_api.py
└── e2e/
    └── test_purchase_flow.py
```

---

## Success Criteria

### Technical Metrics

- [ ] **SOLID Score**: 80+ (from 45)
- [ ] **Test Coverage**: 80%+ (from ~40%)
- [ ] **View LOC**: All < 500 lines (from 2,387 and 3,443)
- [ ] **Service Coverage**: 100% of business logic in services
- [ ] **Cyclomatic Complexity**: < 10 per function (from 15+)

### Performance Metrics

- [ ] **Response Time**: Maintained or improved (< 5% regression)
- [ ] **Database Queries**: Reduced N+1 queries by 80%
- [ ] **Error Rate**: < 0.1% (production)
- [ ] **Uptime**: 99.9%+ during refactoring

### Quality Metrics

- [ ] **Code Review**: All PRs reviewed by 2+ developers
- [ ] **Documentation**: All services documented
- [ ] **Deprecation Warnings**: 0 in production
- [ ] **Security Vulnerabilities**: 0 critical/high

---

## Risk Mitigation

### Rollback Plan

1. **Feature Flags**: All changes behind feature flags
2. **Parallel Run**: Old + new code side-by-side for 1 week
3. **Gradual Rollout**: 10% → 50% → 100% traffic
4. **Quick Rollback**: Single config change reverts to old code

### Monitoring

```python
# Add metrics to all services
from utils.metrics import track_performance

class CatalogService:
    @track_performance('catalog.create_product')
    def create_product(self, user, data):
        # Implementation
```

**Dashboards**:
- Service response times
- Error rates by service
- Database query counts
- Storage upload success rate

---

## Next Phase

Upon completion of Phase 1, proceed to:
- [PHASE2_BOUNDED_CONTEXTS.md](./PHASE2_BOUNDED_CONTEXTS.md)

---

**Document Status**: Complete
**Last Updated**: 2025-11-29
