"""
Abstract base class for authentication providers.

Defines the contract for external identity providers (Google, Apple, etc.),
adhering to the Dependency Inversion Principle.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AuthProvider(ABC):
    """Interface for external authentication providers."""

    @abstractmethod
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify the provider's token.

        Args:
            token: The token string received from the frontend/client.

        Returns:
            A dictionary containing user info (email, name, etc.) if valid,
            None otherwise.
        """
        pass
