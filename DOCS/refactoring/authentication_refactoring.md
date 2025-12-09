# Refactoring Plan: Authentication (Identity Bounded Context)

**Status**: Planning
**Target Context**: Identity Context
**Owner**: Backend Team

## Overview

This document outlines the comprehensive refactoring plan for the `authentication` app, transforming it into a robust **Identity Bounded Context**. This plan integrates the strategies from **Phase 1 (SOLID Refactoring)**, **Phase 2 (Bounded Contexts)**, and **Phase 3 (Microservices Extraction)**.

**Note on Phase 3**: While the [Microservices Extraction Strategy](../PHASE3_MICROSERVICES_EXTRACTION.md) advises **against** extracting Identity/Auth as a standalone microservice in the initial wave (due to its critical path nature), this plan prepares the module to function as a logically isolated component (Modular Monolith) that integrates with the API Gateway and Event Bus, ready for future extraction if scaling demands it.

---

## Current State Analysis

The `authentication` app is currently a monolithic Django app containing mixed concerns:
- **Models**: Mixed User, Profile, and Seller logic (`models.py`, `seller_models.py`).
- **Views**: Thick controllers with business logic (`api_views.py`, `views.py`, `seller_views.py`).
- **Utils**: Helper functions acting as procedural services (`utils.py`, `google_auth.py`).
- **Coupling**: High coupling between HTTP handling, business rules, and infrastructure (email, S3).

---

## Phase 1: SOLID Refactoring (Weeks 1-4)

**Goal**: Extract business logic into a dedicated Service Layer and segregate interfaces.

### 1.1 Infrastructure Abstraction (Dependency Inversion)
Create abstraction layers for external tools to decouple the core domain from implementation details.

- [ ] **Email Infrastructure**:
  - Create `infra/mail/email_interface.py` (Abstract Base Class).
  - Move email logic from `utils.py` to `infra/mail/smtp_service.py`.
  - Create `MockEmailService` for testing.
- [ ] **Storage Infrastructure**:
  - Extract S3 logic (profile pictures) from `models.py`/`views.py` to `infra/storage/`.
- [ ] **OAuth Infrastructure**:
  - Refactor `google_auth.py` and `services/google_oauth.py` into `infra/oauth/google_provider.py`.

### 1.2 Service Layer Extraction (Single Responsibility)
Remove business logic from Views and Models.

- [ ] **AuthService**:
  - Create `domain/services/auth_service.py`.
  - Methods: `login()`, `register()`, `verify_email()`, `handle_2fa()`.
  - Move logic from `LoginAPIView` and `RegisterAPIView`.
- [ ] **ProfileService**:
  - Create `domain/services/profile_service.py`.
  - Methods: `update_profile()`, `upload_avatar()`.
- [ ] **SellerService**:
  - Create `domain/services/seller_service.py`.
  - Methods: `submit_application()`, `approve_application()`, `reject_application()`.

### 1.3 Serializer Segregation (Interface Segregation)
Break down "fat" serializers into specific contracts.

- [ ] Refactor `UserSerializer` into:
  - `UserLoginSerializer`
  - `UserRegistrationSerializer`
  - `UserPublicProfileSerializer`
- [ ] Refactor `SellerApplicationSerializer` into:
  - `SellerApplicationCreateSerializer`
  - `SellerApplicationReviewSerializer` (includes admin fields)

### 1.4 Testing (SOLID Score)
- [ ] Write Unit Tests for all new Services (Mock infrastructure).
- [ ] Write Integration Tests for API Views.
- [ ] Achieve 80%+ coverage.

---

## Phase 2: Bounded Context Implementation (Weeks 5-8)

**Goal**: Reorganize the physical structure to reflect the Domain-Driven Design "Identity Context" and implement Event-Driven Architecture.

### 2.1 Directory Structure Reorganization
Adopt the Domain/API/Infra layered architecture.

```text
authentication/
├── domain/                  # Pure Business Logic
│   ├── models/              # CustomUser, Profile, SellerApplication
│   ├── services/            # AuthService, SellerService
│   ├── events/              # IdentityEvents
│   └── exceptions.py
├── api/                     # Interface Adapters
│   ├── views/               # AuthViews, SellerViews
│   ├── serializers/         # Request/Response DTOs
│   └── urls/
├── infra/                   # Frameworks & Drivers
│   ├── mail/
│   ├── storage/
│   ├── oauth/
│   └── security/            # JWT, Password validators
└── tests/
```

### 2.2 Domain Events Implementation
Decouple the Identity context from other contexts (like Notifications or Marketplace) using events.

- [ ] **Define Events**:
  - `UserRegisteredEvent`
  - `UserVerifiedEvent`
  - `SellerApplicationApprovedEvent`
  - `UserLoginDetectedEvent`
- [ ] **Event Publishing**:
  - Update `AuthService` and `SellerService` to publish events to the Redis Event Bus.
  - *Example*: When `SellerService.approve_application()` is called, publish `seller.approved` instead of directly modifying `Marketplace` data.

### 2.3 Decoupling Models
Ensure `authentication` models do not depend on foreign keys from other contexts.
- *Check*: Ensure `SellerApplication` does not link to `Marketplace` models directly (if applicable).
- *Action*: Use UUID references if cross-context linking is needed.

---

## Phase 3: Integration & Gateway Preparation (Weeks 9-10)

**Goal**: Finalize the Identity Module as a "Logical Microservice" and integrate with the API Gateway.

### 3.1 API Gateway Integration (Kong)
Configure the API Gateway to handle routing and potentially offload common tasks.

- [ ] **Route Configuration**:
  - Map `/api/v1/auth/*` to the Authentication module.
- [ ] **Rate Limiting**:
  - Configure Kong rate-limiting plugins for `/login` and `/register` endpoints (e.g., 5 requests/minute).
- [ ] **Centralized Authentication (Preparation)**:
  - Ensure the JWT structure is standard and parsable by the Gateway.
  - Prepare a "Verify Token" internal endpoint or shared library that the Gateway or other services can use for high-speed validation.

### 3.2 Internal Interface for Monolith
Since other services (Orders, Catalog) need user info, provide a clean interface.

- [ ] **IdentityServiceInterface**:
  - Implement the interface defined in `PHASE2_BOUNDED_CONTEXTS.md`.
  - `get_user(user_id) -> dict`
  - `validate_token(token) -> bool`
  - This prevents other modules from importing `authentication.models.CustomUser` directly.

### 3.3 Observability
- [ ] **Distributed Tracing**:
  - Instrument `AuthService` with OpenTelemetry.
  - Track `login` latency and success rates.
- [ ] **Metrics**:
  - Expose Prometheus metrics: `auth_login_total`, `auth_login_failed`, `seller_applications_pending`.

---

## Execution Checklist

### Week 1-2: Service Layer & Infrastructure
- [ ] Create `infra/` structure and move Email/S3 logic.
- [ ] Create `domain/services/auth_service.py` and move login/register logic.
- [ ] Create `domain/services/seller_service.py`.

### Week 3-4: API & Testing
- [ ] Refactor Views to use Services.
- [ ] Split Serializers.
- [ ] Write Service Layer Unit Tests.

### Week 5-6: Structure & Events
- [ ] Move files to `authentication/domain/`, `authentication/api/`.
- [ ] Fix all imports.
- [ ] Implement `EventBus` publishing in Services.

### Week 7-8: Gateway & Interfaces
- [ ] Create `IdentityService` adapter for other modules.
- [ ] Configure Gateway routes (Kong).
- [ ] Add OpenTelemetry instrumentation.

## Rollback Plan
- Changes will be performed on a separate branch `refactor/authentication`.
- The `old_views.py` will be kept until full regression testing passes.
- Feature flags will be used for switching between `OldAuthLogic` and `NewAuthService` if strictly necessary, though usually, a clean cutover is preferred for Auth.
