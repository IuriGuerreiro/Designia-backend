from __future__ import annotations

from typing import Iterable, Set

from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

UserModel = get_user_model()


def _fetch_persisted_role(user: UserModel) -> str | None:
    """Load the latest role from the database to avoid trusting JWT claims."""
    try:
        return (
            user.__class__.objects.filter(pk=user.pk).values_list("role", flat=True).first()
        )
    except Exception:
        return getattr(user, "role", None)


def build_role_set(user: UserModel) -> Set[str]:
    """Compute the full role set for the given user instance."""
    cached = getattr(user, "_cached_role_set", None)
    if cached is not None:
        return cached

    roles: Set[str] = set()
    if not getattr(user, "is_authenticated", False):
        return roles

    roles.add("user")

    persisted_role = _fetch_persisted_role(user)
    if persisted_role:
        roles.add(str(persisted_role))

    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        roles.add("admin")

    try:
        if user.can_sell_products():
            roles.add("seller")
    except AttributeError:
        if getattr(user, "role", None) == "seller":
            roles.add("seller")

    setattr(user, "_cached_role_set", roles)
    return roles


def user_has_role(user: UserModel, *required: str) -> bool:
    roles = build_role_set(user)
    return any(role in roles for role in required)


class RoleRequired(BasePermission):
    """Base permission that enforces required roles after DB re-validation."""

    required_roles: Iterable[str] = ()

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False

        required = tuple(self.required_roles)
        if not required:
            return True
        return user_has_role(user, *required)

    def has_object_permission(self, request, view, obj) -> bool:
        return self.has_permission(request, view)


class SellerRequired(RoleRequired):
    required_roles = ("seller", "admin")


class AdminRequired(RoleRequired):
    required_roles = ("admin",)
