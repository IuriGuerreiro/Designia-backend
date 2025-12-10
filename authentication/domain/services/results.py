"""
Result objects for service layer.

Using dataclasses to return structured results from service methods
instead of mixed tuples or dicts. Provides type safety and clarity.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LoginResult:
    """Result of login attempt."""

    success: bool
    user: Optional[Any] = None  # CustomUser instance
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    requires_2fa: bool = False
    code_already_sent: bool = False
    error: Optional[str] = None
    user_id: Optional[str] = None  # For 2FA flow
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class RegisterResult:
    """Result of user registration attempt."""

    success: bool
    user: Optional[Any] = None  # CustomUser instance
    email_sent: bool = False
    error: Optional[str] = None
    errors: Optional[Dict[str, str]] = None  # Field-level errors
    message: Optional[str] = None


@dataclass
class Result:
    """Generic result for simple operations."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = field(default_factory=dict)
    error: Optional[str] = None
