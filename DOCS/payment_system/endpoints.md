# Payment System API

**Base path:** `/api/payments/`

## Checkout & Orders

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/checkout_session/` | Create Stripe Embedded Checkout session for current cart. Locks stock and creates pending order. | Auth header. Body empty; uses cart contents. | `200 OK` JSON `{ clientSecret }`. Errors for empty carts, stock issues, invalid pricing. |
| GET | `/checkout_session/retry/{order_id}/` | Recreate checkout session for a pending payment order. | Auth header. Path `order_id` (UUID). | `200 OK` `{ clientSecret }` when order is pending. |
| POST | `/orders/{order_id}/cancel/` | Cancel an order and refund via Stripe if already paid. | Auth header. JSON: `cancellation_reason`. User must be buyer, seller, or staff. | `200 OK` with cancellation details and optional refund metadata. |

## Stripe Webhooks

| Method | Path | Description | Notes |
| --- | --- | --- | --- |
| POST | `/stripe_webhook/` | Primary Stripe webhook endpoint (payment intent, checkout status, refunds). | Expects Stripe signature header; no client-side use. |
| POST | `/stripe_webhook/connect/` | Stripe Connect webhook for account-level events. | For Stripe only. |

## Stripe Connect Accounts

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/stripe/account/` | Inspect current seller's Stripe Connect account or eligibility. | Auth header. | `200 OK` with `has_account`, status info, and eligibility checks. |
| POST | `/stripe/account/` | Create a Stripe Connect account (if absent) or return existing info. | Auth header. Optional JSON: `country` (ISO2), `business_type` (`individual`/`company`). | `201 Created` when new account created; `200 OK` when account already exists. |
| POST | `/stripe/create-session/` | Create an onboarding/account update session. | Auth header. | `200 OK` with `client_secret`, `account_id`. |
| GET | `/stripe/account-status/` | Quick status check for connected account. | Auth header. | `200 OK` with status flags (`charges_enabled`, `payouts_enabled`, `requirements`). |

## Payment Holds & Transfers

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/stripe/holds/` | List funds on hold for the seller, with release ETA. | Auth header (seller/admin). | `200 OK` with summary totals and per-transaction hold details. |
| POST | `/transfer/` | Trigger transfer of a held payment to seller's account (manual release). | Auth header. JSON: `transaction_id` (UUID), optional `transfer_group`. Must be seller or admin; validates status and order delivery. | `200 OK` with transfer confirmation and Stripe transfer data. |

## Payouts

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/payout/` | Create a Stripe payout from available balance. | Auth header. Sellers need connected account and balance; admins can specify amount/currency in body (`amount` cents, `currency`, optional `description`). | `201 Created` with payout metadata and DB record. |
| GET | `/payouts/` | List payouts for current seller. Supports pagination. | Auth header. Query: `page_size` (<=100), `offset`. | `200 OK` with `payouts` array (summary serializer) and pagination info. |
| GET | `/payouts/{payout_id}/` | Detailed payout view with associated transfers. | Auth header. Path UUID `payout_id`. | `200 OK` with `payout` (including items and totals). |
| GET | `/payouts/{payout_id}/orders/` | Orders/items included in a payout (seller-only). | Auth header. | `200 OK` with filtered order list and amounts. |

## Admin Oversight

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/admin/payouts/` | Admin view of all payouts with filters. | Admin auth. Query: `status`, `seller_id`, `from_date`, `to_date`, `page_size`, `offset`, `search`. | `200 OK` with payout summaries, seller info, pagination, aggregated totals. |
| GET | `/admin/transactions/` | Admin view of all payment transactions. | Admin auth. Query filters: `status`, `seller_id`, `buyer_id`, `from_date`, `to_date`, `page_size`, `offset`, `search`. | `200 OK` with transaction records and summary stats. |

_Notes:_ All payment endpoints rely on Stripe services defined in `payment_system`. Many responses include diagnostic fields in debug mode; production clients should rely on documented keys above.
