from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class PaymentProvider(ABC):
    @abstractmethod
    def create_checkout_session(
        self,
        line_items: list[dict[str, Any]],
        customer_email: str,
        mode: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[dict[str, Any]] = None,
        payment_intent_data: Optional[dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a session for the user to pay."""
        pass

    @abstractmethod
    def create_transfer(self, destination_id: str, amount: int, currency: str, metadata: Dict) -> str:
        """Transfer funds to a connected account."""
        pass

    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str, endpoint_secret: str) -> Dict[str, Any]:
        """Verify webhook signature and return event data."""
        pass

    @abstractmethod
    def get_account_balance(self, account_id: str) -> Dict[str, int]:
        """Get available and pending balance."""
        pass

    @abstractmethod
    def retrieve_checkout_session(self, session_id: str) -> Dict[str, Any]:
        """Retrieve a checkout session by ID."""
        pass

    @abstractmethod
    def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create a refund for a payment intent."""
        pass

    @abstractmethod
    def create_connected_account(self, email: str, country: str, business_type: str, **kwargs) -> Dict[str, Any]:
        """Create a Stripe connected account."""
        pass

    @abstractmethod
    def create_account_session(
        self, account_id: str, components: Dict[str, Any], settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Stripe account session."""
        pass

    @abstractmethod
    def retrieve_account(self, account_id: str) -> Dict[str, Any]:
        """Retrieve a Stripe account details."""
        pass

    @abstractmethod
    def retrieve_balance(self) -> Dict[str, Any]:
        """Retrieve the platform's balance."""
        pass

    @abstractmethod
    def retrieve_payment_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        """Retrieve a payment intent by ID."""
        pass
