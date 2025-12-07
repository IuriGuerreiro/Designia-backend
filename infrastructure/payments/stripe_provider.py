"""
Stripe Payment Provider
========================

Concrete implementation of PaymentProviderInterface using Stripe.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import stripe
from django.conf import settings
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .interface import (
    CheckoutSession,
    PaymentException,
    PaymentIntent,
    PaymentProviderInterface,
    PaymentStatus,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProviderInterface):
    """
    Stripe payment provider implementation.

    Configuration (in settings.py):
        STRIPE_SECRET_KEY: Stripe secret API key
        STRIPE_PUBLISHABLE_KEY: Stripe publishable key
        STRIPE_WEBHOOK_SECRET: Webhook endpoint secret for signature verification
    """

    def __init__(self):
        """Initialize Stripe provider with API credentials."""
        stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
        self.webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

        if not stripe.api_key:
            logger.warning("STRIPE_SECRET_KEY not configured")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                stripe.error.RateLimitError,
                stripe.error.APIConnectionError,
                stripe.error.APIError,
            )
        ),
        reraise=True,
    )
    def _create_checkout_session_api(self, **kwargs):
        """Internal method to create session with retries."""
        return stripe.checkout.Session.create(**kwargs)

    def create_checkout_session(
        self,
        amount: Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        customer_email: Optional[str] = None,
    ) -> CheckoutSession:
        """
        Create a Stripe checkout session.

        Args:
            amount: Payment amount in major currency unit (e.g., 10.50 USD)
            currency: ISO currency code (lowercase)
            success_url: Redirect URL on success
            cancel_url: Redirect URL on cancel
            metadata: Custom metadata
            customer_email: Customer email

        Returns:
            CheckoutSession object

        Raises:
            PaymentException: If session creation fails
        """
        try:
            # Convert amount to cents (smallest currency unit)
            amount_cents = int(amount * 100)

            # Build session parameters
            session_params = {
                "payment_method_types": ["card"],
                "line_items": [
                    {
                        "price_data": {
                            "currency": currency.lower(),
                            "unit_amount": amount_cents,
                            "product_data": {
                                "name": "Order Payment",
                            },
                        },
                        "quantity": 1,
                    }
                ],
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
            }

            # Add optional parameters
            if metadata:
                session_params["metadata"] = metadata

            if customer_email:
                session_params["customer_email"] = customer_email

            # Create Stripe checkout session with retry logic
            session = self._create_checkout_session_api(**session_params)

            logger.info(f"Created Stripe checkout session: {session.id}")

            return CheckoutSession(
                session_id=session.id,
                url=session.url,
                amount=amount_cents,
                currency=currency.lower(),
                status=self._map_stripe_status(session.payment_status),
                metadata=metadata or {},
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe session creation failed: {str(e)}")
            raise PaymentException(f"Failed to create checkout session: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error creating session: {str(e)}")
            raise PaymentException(f"Session creation error: {str(e)}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                stripe.error.RateLimitError,
                stripe.error.APIConnectionError,
                stripe.error.APIError,
            )
        ),
        reraise=True,
    )
    def _retrieve_session_api(self, session_id):
        return stripe.checkout.Session.retrieve(session_id)

    def retrieve_session(self, session_id: str) -> CheckoutSession:
        """
        Retrieve an existing Stripe checkout session.

        Args:
            session_id: Stripe session ID

        Returns:
            CheckoutSession object

        Raises:
            PaymentException: If retrieval fails
        """
        try:
            session = self._retrieve_session_api(session_id)

            logger.info(f"Retrieved Stripe session: {session_id}")

            return CheckoutSession(
                session_id=session.id,
                url=session.url or "",
                amount=session.amount_total,
                currency=session.currency,
                status=self._map_stripe_status(session.payment_status),
                metadata=session.metadata or {},
            )

        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve session {session_id}: {str(e)}")
            raise PaymentException(f"Session retrieval failed: {str(e)}") from e

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """
        Verify Stripe webhook signature and parse event.

        Args:
            payload: Raw webhook payload bytes
            signature: Stripe-Signature header value

        Returns:
            Verified WebhookEvent

        Raises:
            PaymentException: If verification fails
        """
        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(payload, signature, self.webhook_secret)

            logger.info(f"Verified Stripe webhook event: {event['type']}")

            return WebhookEvent(
                event_id=event["id"],
                event_type=event["type"],
                data=event["data"]["object"],
                created_at=event["created"],
            )

        except ValueError as e:
            logger.error(f"Invalid webhook payload: {str(e)}")
            raise PaymentException("Invalid webhook payload") from e
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {str(e)}")
            raise PaymentException("Webhook signature verification failed") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                stripe.error.RateLimitError,
                stripe.error.APIConnectionError,
                stripe.error.APIError,
            )
        ),
        reraise=True,
    )
    def _create_refund_api(self, **kwargs):
        return stripe.Refund.create(**kwargs)

    def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Create a refund in Stripe.

        Args:
            payment_intent_id: Stripe payment intent ID
            amount: Partial refund amount (None for full refund)
            reason: Refund reason

        Returns:
            True if refund created successfully

        Raises:
            PaymentException: If refund creation fails
        """
        try:
            refund_params = {
                "payment_intent": payment_intent_id,
            }

            if amount:
                refund_params["amount"] = int(amount * 100)

            if reason:
                refund_params["reason"] = reason

            refund = self._create_refund_api(**refund_params)

            logger.info(f"Created refund: {refund.id} for payment {payment_intent_id}")

            return refund.status == "succeeded"

        except stripe.error.StripeError as e:
            logger.error(f"Refund creation failed: {str(e)}")
            raise PaymentException(f"Refund failed: {str(e)}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                stripe.error.RateLimitError,
                stripe.error.APIConnectionError,
                stripe.error.APIError,
            )
        ),
        reraise=True,
    )
    def _create_transfer_api(self, **kwargs):
        return stripe.Transfer.create(**kwargs)

    def create_transfer(
        self,
        amount: Decimal,
        currency: str,
        destination_account: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a transfer to a connected account.

        Args:
            amount: Amount to transfer
            currency: Currency code
            destination_account: Destination Stripe account ID
            metadata: Optional metadata

        Returns:
            Transfer details dictionary

        Raises:
            PaymentException: If transfer fails
        """
        try:
            amount_cents = int(amount * 100)

            transfer_params = {
                "amount": amount_cents,
                "currency": currency.lower(),
                "destination": destination_account,
            }

            if metadata:
                transfer_params["metadata"] = metadata

            transfer = self._create_transfer_api(**transfer_params)

            logger.info(f"Created Stripe transfer: {transfer.id} to {destination_account}")

            return {
                "id": transfer.id,
                "amount": transfer.amount,
                "currency": transfer.currency,
                "destination": transfer.destination,
                "status": "succeeded",  # Transfers are synchronous
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe transfer failed: {str(e)}")
            raise PaymentException(f"Transfer failed: {str(e)}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                stripe.error.RateLimitError,
                stripe.error.APIConnectionError,
                stripe.error.APIError,
            )
        ),
        reraise=True,
    )
    def _retrieve_payment_intent_api(self, intent_id):
        return stripe.PaymentIntent.retrieve(intent_id)

    def retrieve_payment_intent(self, intent_id: str) -> PaymentIntent:
        """
        Retrieve Stripe payment intent details.

        Args:
            intent_id: Payment intent ID

        Returns:
            PaymentIntent object

        Raises:
            PaymentException: If retrieval fails
        """
        try:
            intent = self._retrieve_payment_intent_api(intent_id)

            logger.info(f"Retrieved payment intent: {intent_id}")

            return PaymentIntent(
                intent_id=intent.id,
                amount=intent.amount,
                currency=intent.currency,
                status=self._map_stripe_payment_status(intent.status),
                customer_email=intent.receipt_email,
                metadata=intent.metadata or {},
            )

        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve payment intent {intent_id}: {str(e)}")
            raise PaymentException(f"Payment intent retrieval failed: {str(e)}") from e

    def _map_stripe_status(self, stripe_status: str) -> PaymentStatus:
        """
        Map Stripe session payment status to internal PaymentStatus.

        Args:
            stripe_status: Stripe payment status string

        Returns:
            PaymentStatus enum value
        """
        status_mapping = {
            "unpaid": PaymentStatus.PENDING,
            "paid": PaymentStatus.SUCCEEDED,
            "no_payment_required": PaymentStatus.SUCCEEDED,
        }

        return status_mapping.get(stripe_status, PaymentStatus.PENDING)

    def _map_stripe_payment_status(self, stripe_status: str) -> PaymentStatus:
        """
        Map Stripe payment intent status to internal PaymentStatus.

        Args:
            stripe_status: Stripe payment intent status

        Returns:
            PaymentStatus enum value
        """
        status_mapping = {
            "requires_payment_method": PaymentStatus.PENDING,
            "requires_confirmation": PaymentStatus.PENDING,
            "requires_action": PaymentStatus.PROCESSING,
            "processing": PaymentStatus.PROCESSING,
            "requires_capture": PaymentStatus.PROCESSING,
            "canceled": PaymentStatus.CANCELED,
            "succeeded": PaymentStatus.SUCCEEDED,
        }

        return status_mapping.get(stripe_status, PaymentStatus.FAILED)
