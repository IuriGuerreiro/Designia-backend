import logging
from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

# Canonical role names
ROLE_USER = "user"
ROLE_SELLER = "seller"
ROLE_ADMIN = "admin"

logger = logging.getLogger(__name__)


def _fetch_user_from_db(user):
    """Fetch a fresh copy of the user from the DB with only the fields we need.

    Falls back to None if user is not authenticated or lookup fails.
    """
    try:
        if not getattr(user, "is_authenticated", False):
            return None
        User = get_user_model()
        # Only load minimal fields required for RBAC checks
        return User.objects.only("id", "role", "is_superuser").filter(pk=getattr(user, "pk", None)).first()
    except Exception:
        return None


def is_admin(user) -> bool:
    """Consistent admin check across the codebase, verified against the database."""
    try:
        db_user = _fetch_user_from_db(user)
        if not db_user:
            return False
        return bool(getattr(db_user, "is_superuser", False) or getattr(db_user, "role", None) == ROLE_ADMIN)
    except Exception:
        # Conservative fallback
        return bool(getattr(user, "is_superuser", False))


def is_seller(user) -> bool:
    """Consistent seller check across the codebase, verified against the database.

    Admins are considered sellers as well.
    """
    try:
        # Prefer the domain capability when available
        if hasattr(user, "can_sell_products"):
            return bool(user.can_sell_products())

        db_user = _fetch_user_from_db(user)
        if not db_user:
            return False
        return getattr(db_user, "role", None) == ROLE_SELLER or is_admin(user)
    except Exception:
        return False


def has_role(user, role: str) -> bool:
    if role == ROLE_ADMIN:
        return is_admin(user)
    if role == ROLE_SELLER:
        return is_seller(user)
    db_user = _fetch_user_from_db(user)
    return getattr(db_user, "role", None) == role if db_user else False


def has_any_role(user, roles: Iterable[str]) -> bool:
    return any(has_role(user, r) for r in roles)


def require_role(user, roles: Iterable[str]):
    """Raise PermissionDenied unless the user has one of the roles."""
    if not has_any_role(user, roles):
        logger.warning(
            "RBAC denial: user_id=%s required=%s",
            getattr(user, "id", None),
            list(roles),
        )
        raise PermissionDenied("Insufficient role to access this resource.")


# Convenience specific guards
def require_admin(user):
    require_role(user, [ROLE_ADMIN])


def require_seller(user):
    require_role(user, [ROLE_SELLER, ROLE_ADMIN])
