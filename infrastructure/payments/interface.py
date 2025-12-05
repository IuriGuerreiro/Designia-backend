"""
Payment Provider Interface
===========================

Abstract base class defining the contract for payment operations.
Implements the Interface Segregation Principle for payment processing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class PaymentStatus(str, Enum):
    """Payment status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"


@dataclass
class CheckoutSession:
    """
    Represents a payment checkout session.

    Attributes:
        session_id: Unique session identifier
        url: Redirect URL for customer to complete payment
        amount: Payment amount in smallest currency unit (cents)
        currency: ISO currency code (e.g., 'usd')
        status: Current status of the session
        metadata: Additional custom data
    """

    session_id: str
    url: str
    amount: int
    currency: str
    status: PaymentStatus
    metadata: Dict[str, Any]


@dataclass
class PaymentIntent:
    """
    Represents a payment intent/transaction.

    Attributes:
        intent_id: Unique payment intent identifier
        amount: Payment amount in smallest currency unit
        currency: ISO currency code
        status: Current payment status
        customer_email: Customer's email address
        metadata: Additional custom data
    """

    intent_id: str
    amount: int
    currency: str
    status: PaymentStatus
    customer_email: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class WebhookEvent:
    """
    Represents a webhook event from payment provider.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event (e.g., 'payment.succeeded')
        data: Event payload data
        created_at: Event creation timestamp
    """

    event_id: str
    event_type: str
    data: Dict[str, Any]
    created_at: int


class PaymentProviderInterface(ABC):
    """
    Abstract interface for payment provider operations.

    Concrete implementations:
        - StripeProvider: Stripe payment processing
        - PayPalProvider: PayPal payment processing (future)
    """

    @abstractmethod
    def create_checkout_session(
        self,
        amount: Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        customer_email: Optional[str] = None,
        line_items: Optional[List[Dict[str, Any]]] = None,
    ) -> CheckoutSession:
        """
        Create a payment checkout session.

        Args:
            amount: Payment amount (will be converted to smallest currency unit)
            currency: ISO currency code
            success_url: Redirect URL on successful payment
            cancel_url: Redirect URL on canceled payment
            metadata: Custom data to attach to session
            customer_email: Pre-fill customer email
            line_items: Optional list of line items for the checkout session

        Returns:
            CheckoutSession object with session details

        Raises:
            PaymentException: If session creation fails
        """
        pass

    @abstractmethod
    def retrieve_session(self, session_id: str) -> CheckoutSession:
        """
        Retrieve an existing checkout session.

        Args:
            session_id: Session identifier to retrieve

        Returns:
            CheckoutSession object

        Raises:
            PaymentException: If retrieval fails
        """
        pass

    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """
        Verify and parse webhook event from payment provider.

        Args:
            payload: Raw webhook payload bytes
            signature: Webhook signature header for verification

        Returns:
            Parsed and verified WebhookEvent

        Raises:
            PaymentException: If verification fails or signature is invalid
        """
        pass

    @abstractmethod
    def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Create a refund for a payment.

        Args:
            payment_intent_id: Payment intent to refund
            amount: Partial refund amount (None for full refund)
            reason: Refund reason

        Returns:
            True if refund created successfully

        Raises:
            PaymentException: If refund creation fails
        """
        pass

    @abstractmethod
    def create_transfer(
        self,
        amount: Decimal,
        currency: str,
        destination_account: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a transfer to a connected account (e.g. seller payout).

        Args:
            amount: Amount to transfer
            currency: Currency code
            destination_account: Destination account ID (e.g. Stripe Connect ID)
            metadata: Optional metadata

        Returns:
            Dictionary with transfer details

        Raises:
            PaymentException: If transfer fails
        """
        pass

    @abstractmethod
    def retrieve_payment_intent(self, intent_id: str) -> PaymentIntent:
        """
        Retrieve payment intent details.

        Args:
            intent_id: Payment intent identifier

        Returns:
            PaymentIntent object

        Raises:
            PaymentException: If retrieval fails
        """
        pass


class PaymentException(Exception):
    """Base exception for payment operations."""

    pass
