"""
Shared service-layer utilities to encourage separation of concerns.

This module provides a minimal, dependency-free foundation for building
services in each Django app. Adopt this pattern incrementally by moving
business logic out of views/serializers into small, testable service
functions or classes.

Guidelines
- Keep services stateless; pass dependencies via parameters.
- Return structured results instead of raising for expected outcomes.
- Reserve exceptions for truly exceptional/unrecoverable scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ServiceResult(Generic[T]):
    """Standard wrapper for service outcomes.

    - value: payload on success (may be None for void operations)
    - error: short error code or message suitable for API mapping
    - detail: optional human/debug detail (never log secrets/PII)
    """

    value: Optional[T] = None
    error: Optional[str] = None
    detail: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def service_ok(value: Optional[T] = None) -> ServiceResult[T]:
    return ServiceResult(value=value)


def service_err(code: str, detail: Optional[str] = None) -> ServiceResult[T]:
    return ServiceResult(error=code, detail=detail)


class ServiceError(Exception):
    """Raised for unrecoverable service conditions.

    Prefer returning ServiceResult for expected failures. Raise ServiceError
    only for conditions the caller cannot gracefully handle.
    """

    pass
