"""
Infrastructure Package
======================

Provides abstraction layers for external dependencies following the Dependency Inversion Principle.

Modules:
    - storage: File storage abstraction (S3, local filesystem)
    - email: Email service abstraction (SMTP, mock)
    - payments: Payment provider abstraction (Stripe)
    - notifications: Notification service abstraction

This package enables:
    - Easy testing with mock implementations
    - Switching between providers without code changes
    - Loose coupling between business logic and infrastructure
"""
