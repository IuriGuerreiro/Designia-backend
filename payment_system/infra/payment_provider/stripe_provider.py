import logging
import uuid
from typing import Any, Dict, Optional

import stripe
from django.conf import settings

from authentication.infra.observability.tracing import tracer
from payment_system.infra.payment_provider.interface import PaymentProvider


logger = logging.getLogger(__name__)

stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")


class StripePaymentProvider(PaymentProvider):
    @tracer.start_as_current_span("StripePaymentProvider.create_checkout_session")
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
        """
        Create a session for the user to pay using Stripe Checkout.
        """
        with tracer.start_as_current_span("stripe_api_checkout_session_create") as span:
            span.set_attribute("stripe.customer_email", customer_email)
            span.set_attribute("stripe.mode", mode)
            span.set_attribute("stripe.metadata", str(metadata))
            span.set_attribute("stripe.line_item_count", len(line_items))

            try:
                session_params = {
                    "ui_mode": "embedded",
                    "line_items": line_items,
                    "customer_email": customer_email,
                    "mode": mode,
                    "return_url": success_url,  # Stripe embedded checkout uses return_url for success
                    "cancel_url": cancel_url,
                    "metadata": metadata,
                    "idempotency_key": f"checkout_{metadata.get('order_id') or 'unknown'}_{str(uuid.uuid4())}",
                }

                if payment_intent_data:
                    session_params["payment_intent_data"] = payment_intent_data

                # Add any extra kwargs passed
                session_params.update(kwargs)

                session = stripe.checkout.Session.create(**session_params)
                span.set_attribute("stripe.session_id", session.id)
                return {"clientSecret": session.client_secret, "sessionId": session.id}
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error creating checkout session: {str(e)}")
                raise ConnectionError(f"Failed to create checkout session with Stripe: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating checkout session: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred during checkout session creation: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.create_transfer")
    def create_transfer(self, destination_id: str, amount: int, currency: str, metadata: Optional[Dict]) -> str:
        """
        Transfer funds to a connected account.
        Logic moved from create_transfer_to_connected_account in stripe_service.py.
        """
        with tracer.start_as_current_span("stripe_api_transfer_create") as span:
            span.set_attribute("stripe.destination_id", destination_id)
            span.set_attribute("stripe.amount", amount)
            span.set_attribute("stripe.currency", currency)
            span.set_attribute("stripe.metadata", str(metadata))

            logger.info(f"Creating transfer of {amount} {currency} to account {destination_id}")

            try:
                # Validate inputs
                if not destination_id:
                    raise ValueError("Destination account ID is required")

                if amount <= 0:
                    raise ValueError("Transfer amount must be greater than 0")

                # Prepare transfer parameters
                transfer_params = {
                    "amount": amount,
                    "currency": currency.lower(),
                    "destination": destination_id,
                    "idempotency_key": f"transfer_{metadata.get('transaction_id') or metadata.get('order_id') or str(uuid.uuid4())}",
                }

                # Add optional parameters
                if metadata:
                    transfer_params["metadata"] = metadata

                logger.info(f"Transfer parameters: {transfer_params}")
                # Create the transfer
                transfer = stripe.Transfer.create(**transfer_params)

                logger.info(f"Transfer created successfully: {transfer.id}")
                logger.info(f"Transfer status: {transfer.object}")

                return transfer.id

            except stripe.error.StripeError as e:
                logger.error(f"Stripe error creating transfer: {str(e)}")
                raise ConnectionError(f"Failed to create transfer with Stripe: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating transfer: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred during transfer creation: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.verify_webhook")
    def verify_webhook(self, payload: bytes, signature: str, endpoint_secret: str) -> Dict[str, Any]:
        """
        Verify webhook signature and return event data.
        Logic moved from views.py.
        """
        with tracer.start_as_current_span("stripe_api_webhook_verify") as span:
            span.set_attribute("stripe.signature_provided", bool(signature))

            if not endpoint_secret:
                raise ValueError("Stripe webhook secret not configured.")
            if not signature:
                raise ValueError("Missing stripe-signature header.")

            try:
                event = stripe.Webhook.construct_event(payload, signature, endpoint_secret)
                span.set_attribute("stripe.event_type", event.get("type"))
                span.set_attribute("stripe.event_id", event.get("id"))
                return event
            except stripe.error.SignatureVerificationError as e:
                raise ValueError(f"Webhook signature verification failed: {str(e)}") from e
            except ValueError as e:
                raise ValueError(f"Invalid webhook payload: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.get_account_balance")
    def get_account_balance(self, account_id: str) -> Dict[str, int]:
        """
        Get available and pending balance for a connected account.
        """
        with tracer.start_as_current_span("stripe_api_get_account_balance") as span:
            span.set_attribute("stripe.account_id", account_id)
            try:
                balance = stripe.Balance.retrieve(stripe_account=account_id)
                return {
                    "available": [b.amount for b in balance["available"] if b.currency == "usd"][0],
                    "pending": [b.amount for b in balance["pending"] if b.currency == "usd"][0],
                }
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrieving account balance for account {account_id}: {str(e)}")
                raise ConnectionError(f"Failed to retrieve account balance from Stripe: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error retrieving account balance for account {account_id}: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred during balance retrieval: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.retrieve_checkout_session")
    def retrieve_checkout_session(self, session_id: str) -> Dict[str, Any]:
        """
        Retrieve a checkout session by ID.
        Logic moved from views.py to encapsulate Stripe SDK calls.
        """
        with tracer.start_as_current_span("stripe_api_retrieve_checkout_session") as span:
            span.set_attribute("stripe.session_id", session_id)
            try:
                session = stripe.checkout.Session.retrieve(session_id)
                return session
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrieving checkout session {session_id}: {str(e)}")
                raise ConnectionError(f"Failed to retrieve checkout session from Stripe: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error retrieving checkout session {session_id}: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred during session retrieval: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.create_refund")
    def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Create a refund for a payment intent.
        Logic moved from views.py to encapsulate Stripe SDK calls.
        """
        with tracer.start_as_current_span("stripe_api_create_refund") as span:
            span.set_attribute("stripe.payment_intent_id", payment_intent_id)
            span.set_attribute("stripe.amount", amount)
            span.set_attribute("stripe.reason", reason)
            span.set_attribute("stripe.metadata", str(metadata))
            try:
                refund_params = {"payment_intent": payment_intent_id}

                if amount is not None:
                    refund_params["amount"] = amount

                if reason:
                    refund_params["reason"] = reason

                if metadata:
                    refund_params["metadata"] = metadata

                logger.info(f"Creating refund for payment intent {payment_intent_id}")
                refund = stripe.Refund.create(
                    **refund_params, idempotency_key=f"refund_{payment_intent_id}_{reason}_{str(uuid.uuid4())}"
                )
                logger.info(f"Refund created successfully: {refund.id}")

                return refund
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error creating refund for payment intent {payment_intent_id}: {str(e)}")
                raise ConnectionError(f"Failed to create refund with Stripe: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating refund for payment intent {payment_intent_id}: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred during refund creation: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.create_connected_account")
    def create_connected_account(self, email: str, country: str, business_type: str, **kwargs) -> Dict[str, Any]:
        """
        Create a Stripe Express account for a seller.
        """
        with tracer.start_as_current_span("stripe_api_create_connected_account") as span:
            span.set_attribute("stripe.email", email)
            span.set_attribute("stripe.country", country)
            span.set_attribute("stripe.business_type", business_type)
            try:
                account_params = {
                    "country": country,
                    "email": email,
                    "business_type": business_type,
                    "capabilities": {
                        "card_payments": {"requested": True},
                        "transfers": {"requested": True},
                    },
                    "settings": {
                        "payouts": {
                            "schedule": {
                                "interval": "manual",  # Marketplace controls payouts
                            }
                        }
                    },
                    "controller": {
                        "requirement_collection": "application",
                        "losses": {"payments": "application"},
                        "fees": {"payer": "application"},
                        "stripe_dashboard": {"type": "none"},
                    },
                }

                # Add individual info for individual accounts
                if business_type == "individual":
                    account_params["individual"] = {
                        "email": email,
                        "first_name": kwargs.get("first_name", ""),
                        "last_name": kwargs.get("last_name", ""),
                    }

                # Allow overriding defaults
                account_params.update(kwargs)
                # Ensure essential params aren't overwritten if not intended (or rely on caller to be correct)
                # For now, we trust kwargs to add/override as needed.

                logger.info(f"Creating Stripe Connect account for {email}")
                account = stripe.Account.create(**account_params, idempotency_key=f"connect_account_{email}")
                logger.info(f"Stripe Connect account created: {account.id}")

                return account
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error creating connected account: {str(e)}")
                raise ConnectionError(f"Failed to create connected account: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating connected account: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.create_account_session")
    def create_account_session(
        self, account_id: str, components: Dict[str, Any], settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an Account Session for seller onboarding.
        """
        with tracer.start_as_current_span("stripe_api_create_account_session") as span:
            span.set_attribute("stripe.account_id", account_id)
            try:
                session_params = {
                    "account": account_id,
                    "components": components,
                }
                if settings:
                    session_params["settings"] = settings

                logger.info(f"Creating Account Session for {account_id}")
                session = stripe.AccountSession.create(
                    **session_params, idempotency_key=f"account_session_{account_id}_{str(uuid.uuid4())}"
                )
                return session
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error creating account session: {str(e)}")
                raise ConnectionError(f"Failed to create account session: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error creating account session: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.retrieve_account")
    def retrieve_account(self, account_id: str) -> Dict[str, Any]:
        """
        Retrieve a Stripe account details.
        """
        with tracer.start_as_current_span("stripe_api_retrieve_account") as span:
            span.set_attribute("stripe.account_id", account_id)
            try:
                return stripe.Account.retrieve(account_id)
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrieving account {account_id}: {str(e)}")
                raise ConnectionError(f"Failed to retrieve account: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error retrieving account {account_id}: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.retrieve_balance")
    def retrieve_balance(self) -> Dict[str, Any]:
        """
        Retrieve the platform's balance (not a connected account's balance).
        """
        with tracer.start_as_current_span("stripe_api_retrieve_balance"):
            try:
                return stripe.Balance.retrieve()
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrieving platform balance: {str(e)}")
                raise ConnectionError(f"Failed to retrieve platform balance: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error retrieving platform balance: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e

    @tracer.start_as_current_span("StripePaymentProvider.retrieve_payment_intent")
    def retrieve_payment_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Retrieve a payment intent by ID.
        """
        with tracer.start_as_current_span("stripe_api_retrieve_payment_intent") as span:
            span.set_attribute("stripe.payment_intent_id", payment_intent_id)
            try:
                return stripe.PaymentIntent.retrieve(payment_intent_id)
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrieving payment intent {payment_intent_id}: {str(e)}")
                raise ConnectionError(f"Failed to retrieve payment intent: {str(e)}") from e
            except Exception as e:
                logger.error(f"Unexpected error retrieving payment intent {payment_intent_id}: {str(e)}")
                raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e
