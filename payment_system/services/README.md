# Payment Services

This directory contains the Domain Services for the Payment System.

## Services

### `PaymentService`
Orchestrates payment processing, interfacing with payment gateways (Stripe).
- **Key Methods:** `process_payment`, `refund_payment`, `create_payment_intent`
- **Notes:** Wraps external API calls and handles errors.

### `CheckoutService`
Manages the checkout session flow.
- **Key Methods:** `create_checkout_session`, `validate_session`

### `PayoutService`
Handles payouts to sellers (Connect).
- **Key Methods:** `create_payout`, `get_payout_status`

### `WebhookService`
Processes async webhooks from payment providers.
- **Key Methods:** `handle_webhook_event`

## Usage

```python
from payment_system.services.payment_service import PaymentService

def process_order(order):
    result = PaymentService().initiate_payment(order, success_url="...", cancel_url="...")
    if result.ok:
        session = result.value
        # Redirect to session.url
```
