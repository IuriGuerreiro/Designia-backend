from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class PaymentSucceeded:
    order_id: str
    transaction_id: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    shipping_details: dict = None


@dataclass
class PaymentFailed:
    order_id: str
    reason: str
    occurred_at: datetime


@dataclass
class PayoutProcessed:
    seller_id: str
    payout_id: str
    amount: Decimal
    currency: str


@dataclass
class PaymentRefunded:
    order_id: str
    refund_id: str
    amount: Decimal
    currency: str
    reason: str
    occurred_at: datetime


@dataclass
class PaymentRefundFailed:
    order_id: str
    refund_id: str
    reason: str
    amount: Decimal
    currency: str
    occurred_at: datetime
