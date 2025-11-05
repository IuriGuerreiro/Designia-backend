import logging
from typing import Iterable
from django.core.exceptions import PermissionDenied


# Canonical role names
ROLE_USER = 'user'
ROLE_SELLER = 'seller'
ROLE_ADMIN = 'admin'

logger = logging.getLogger(__name__)


def is_admin(user) -> bool:
    """Consistent admin check across the codebase."""
    try:
        return bool(getattr(user, 'is_admin', None) and user.is_admin()) or bool(getattr(user, 'is_superuser', False)) or getattr(user, 'role', None) == ROLE_ADMIN
    except Exception:
        return bool(getattr(user, 'is_superuser', False))


def is_seller(user) -> bool:
    """Consistent seller check across the codebase."""
    try:
        # Prefer the domain capability when available
        if hasattr(user, 'can_sell_products'):
            return bool(user.can_sell_products())
        return getattr(user, 'role', None) == ROLE_SELLER or is_admin(user)
    except Exception:
        return False


def has_role(user, role: str) -> bool:
    if role == ROLE_ADMIN:
        return is_admin(user)
    if role == ROLE_SELLER:
        return is_seller(user)
    return getattr(user, 'role', None) == role


def has_any_role(user, roles: Iterable[str]) -> bool:
    return any(has_role(user, r) for r in roles)


def require_role(user, roles: Iterable[str]):
    """Raise PermissionDenied unless the user has one of the roles."""
    if not has_any_role(user, roles):
        logger.warning("RBAC denial: user_id=%s roles=%s required=%s", getattr(user, 'id', None), getattr(user, 'role', None), list(roles))
        raise PermissionDenied("Insufficient role to access this resource.")


# Convenience specific guards
def require_admin(user):
    require_role(user, [ROLE_ADMIN])


def require_seller(user):
    require_role(user, [ROLE_SELLER, ROLE_ADMIN])

