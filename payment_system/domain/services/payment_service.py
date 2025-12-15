"""
PaymentService - Orchestration Layer for Payments

Orchestrates payment flow, interacting with PaymentProviderInterface and OrderService.
Handles checkout, webhooks, and refunds with atomic transactions.

Story 4.1: PaymentService - Orchestration Layer
"""

import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from infrastructure.events import get_event_bus
from infrastructure.payments.interface import (
    CheckoutSession,
    PaymentException,
    PaymentIntent,
    PaymentProviderInterface,
    PaymentStatus,
)
from marketplace.catalog.domain.services.base import BaseService, ErrorCodes, ServiceResult, service_err, service_ok
from marketplace.models import Order
from payment_system.domain.events.definitions import PaymentRefunded, PaymentSucceeded
from payment_system.infra.observability.metrics import payment_volume_total


logger = logging.getLogger(__name__)


class PaymentService(BaseService):
    """
    Service for orchestrating payment operations.

    Responsibilities:
    - Initiate payments (create checkout sessions)
    - Confirm payments (process webhooks/intents)
    - Refund payments
    - Check payment status
    - Publish payment events for Order state changes

    Dependencies:
    - PaymentProviderInterface: Abstraction for Stripe/PayPal
    - EventBus: For publishing events
    """

    def __init__(
        self,
        payment_provider: PaymentProviderInterface = None,
    ):
        """
        Initialize PaymentService.

        Args:
            payment_provider: Implementation of PaymentProviderInterface
        """
        super().__init__()
        if payment_provider is None:
            # Fallback to getting provider from infrastructure configuration if not provided
            from infrastructure.container import Container

            self.payment_provider = Container.get_payment_provider()
        else:
            self.payment_provider = payment_provider

        self.event_bus = get_event_bus()

    @BaseService.log_performance
    def initiate_payment(self, order: Order, success_url: str, cancel_url: str) -> ServiceResult[CheckoutSession]:
        """
        Initiate a payment flow for an order.

        Creates a checkout session with the payment provider.

        Args:
            order: The order to pay for
            success_url: URL to redirect after success
            cancel_url: URL to redirect after cancellation

        Returns:
            ServiceResult containing CheckoutSession
        """
        try:
            if order.payment_status == "paid":
                return service_err(ErrorCodes.INVALID_ORDER_STATE, "Order is already paid")

            # Map order items to line items
            line_items: List[Dict[str, Any]] = []
            for item in order.items.all():
                line_items.append(
                    {
                        "name": item.product_name,
                        "quantity": item.quantity,
                        "amount": item.unit_price,
                        "currency": "usd",  # Default
                    }
                )

            # Create checkout session
            session = self.payment_provider.create_checkout_session(
                amount=order.total_amount,
                currency="usd",  # Defaulting to USD for now, should come from order or settings
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"order_id": str(order.id)},
                customer_email=order.buyer.email,
                line_items=line_items,
            )

            return service_ok(session)

        except PaymentException as e:
            self.logger.error(f"Payment provider error initiating payment for order {order.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.PAYMENT_PROVIDER_ERROR, str(e))
        except Exception as e:
            self.logger.error(f"Internal error initiating payment for order {order.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def confirm_payment(self, payment_intent_id: str) -> ServiceResult[bool]:
        """
        Confirm a payment success using payment_intent_id (e.g. from webhook).

        Verifies payment status with provider, then publishes PaymentSucceeded event.

        Args:
            payment_intent_id: ID of the payment intent/transaction

        Returns:
            ServiceResult with success boolean
        """
        try:
            # 1. Verify status with provider
            intent: PaymentIntent = self.payment_provider.retrieve_payment_intent(payment_intent_id)

            if intent.status != PaymentStatus.SUCCEEDED:
                return service_err(ErrorCodes.PAYMENT_FAILED, f"Payment not succeeded. Status: {intent.status}")

            # 2. Extract order_id from metadata
            if not intent.metadata or "order_id" not in intent.metadata:
                return service_err(ErrorCodes.INVALID_PAYMENT_DATA, "Order ID missing in payment metadata")

            order_id = intent.metadata["order_id"]

            # 3. Publish Event
            event_payload = PaymentSucceeded(
                order_id=str(order_id),
                transaction_id=payment_intent_id,
                amount=Decimal(str(intent.amount)),
                currency=intent.currency,
                occurred_at=timezone.now(),
                shipping_details={},  # Shipping details might be in intent, need extraction if available
            )
            self.event_bus.publish("payment.succeeded", asdict(event_payload))

            # Increment metric
            payment_volume_total.labels(currency=event_payload.currency, status="succeeded").inc(
                float(event_payload.amount)
            )

            return service_ok(True)

        except PaymentException as e:
            self.logger.error(f"Payment provider error confirming payment {payment_intent_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.PAYMENT_PROVIDER_ERROR, str(e))
        except Exception as e:
            self.logger.error(f"Internal error confirming payment {payment_intent_id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    @transaction.atomic
    def refund_payment(
        self, order: Order, amount: Optional[Decimal] = None, reason: str = None
    ) -> ServiceResult[bool]:
        """
        Refund a payment for an order.

        Args:
            order: The order to refund
            amount: Optional partial refund amount. If None, full refund.
            reason: Reason for refund

        Returns:
            ServiceResult with success boolean
        """
        try:
            if order.payment_status != "paid":
                return service_err(ErrorCodes.INVALID_ORDER_STATE, "Cannot refund unpaid order")

            payment_id = getattr(order, "payment_intent_id", None)
            if not payment_id:
                return service_err(ErrorCodes.INTERNAL_ERROR, "Payment intent ID not found for order")

            # Execute refund with provider
            success = self.payment_provider.create_refund(payment_intent_id=payment_id, amount=amount, reason=reason)

            if success:
                # Publish Event
                event_payload = PaymentRefunded(
                    order_id=str(order.id),
                    refund_id="generated_via_provider",  # Ideally provider returns this
                    amount=amount if amount else order.total_amount,
                    currency="usd",  # Default or extract from order
                    reason=reason or "Refund requested",
                    occurred_at=timezone.now(),
                )
                self.event_bus.publish("payment.refunded", asdict(event_payload))

            return service_ok(success)

        except PaymentException as e:
            self.logger.error(f"Payment provider error refunding order {order.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.PAYMENT_PROVIDER_ERROR, str(e))
        except Exception as e:
            self.logger.error(f"Internal error refunding order {order.id}: {e}", exc_info=True)
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))

    @BaseService.log_performance
    def get_payment_status(self, order: Order) -> ServiceResult[str]:
        """
        Get the current payment status from the provider for an order.

        Args:
            order: The order to check

        Returns:
            ServiceResult with status string
        """
        try:
            payment_id = getattr(order, "payment_intent_id", None)
            if not payment_id:
                return service_ok("unknown")

            intent = self.payment_provider.retrieve_payment_intent(payment_id)
            return service_ok(intent.status)

        except PaymentException as e:
            return service_err(ErrorCodes.PAYMENT_PROVIDER_ERROR, str(e))
        except Exception as e:
            return service_err(ErrorCodes.INTERNAL_ERROR, str(e))
