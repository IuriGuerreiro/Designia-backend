class PaymentError(Exception):
    """Base class for payment system exceptions."""

    pass


class PaymentValidationError(PaymentError):
    """Raised when payment data validation fails."""

    pass


class PaymentProviderError(PaymentError):
    """Raised when the payment provider returns an error."""

    pass


class TransactionError(PaymentError):
    """Raised when a payment transaction fails."""

    pass
