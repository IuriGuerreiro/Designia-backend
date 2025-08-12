"""
Security utilities and middleware for payment processing
"""
import hashlib
import hmac
import time
import logging
from django.conf import settings
from django.http import HttpResponseForbidden
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

class PaymentSecurityMiddleware(MiddlewareMixin):
    """Enhanced security middleware for payment endpoints"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        # Apply security checks only to payment endpoints
        if not request.path.startswith('/api/payments/'):
            return None
        
        # Rate limiting
        if self._is_rate_limited(request):
            logger.warning(f"Rate limit exceeded for IP {self._get_client_ip(request)}")
            return HttpResponseForbidden("Rate limit exceeded")
        
        # IP whitelist for sensitive endpoints
        if self._is_sensitive_endpoint(request.path):
            if not self._is_ip_whitelisted(request):
                logger.warning(f"Unauthorized IP access attempt: {self._get_client_ip(request)}")
                return HttpResponseForbidden("Access denied")
        
        return None
    
    def _get_client_ip(self, request):
        """Get real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _is_rate_limited(self, request):
        """Implement rate limiting for payment endpoints"""
        ip = self._get_client_ip(request)
        
        # Different limits for different endpoints
        if request.path.endswith('/process/'):
            # Payment processing: 10 attempts per minute
            limit, window = 10, 60
        elif request.path.endswith('/create/'):
            # Account creation: 5 attempts per hour
            limit, window = 5, 3600
        else:
            # General endpoints: 100 requests per minute
            limit, window = 100, 60
        
        cache_key = f"rate_limit_{ip}_{request.path}"
        current_attempts = cache.get(cache_key, 0)
        
        if current_attempts >= limit:
            return True
        
        cache.set(cache_key, current_attempts + 1, window)
        return False
    
    def _is_sensitive_endpoint(self, path):
        """Check if endpoint requires additional IP restrictions"""
        sensitive_endpoints = [
            '/api/payments/release-holds/',
            '/api/payments/webhooks/stripe/',
        ]
        return any(path.endswith(endpoint) for endpoint in sensitive_endpoints)
    
    def _is_ip_whitelisted(self, request):
        """Check if IP is whitelisted for sensitive operations"""
        ip = self._get_client_ip(request)
        whitelisted_ips = getattr(settings, 'PAYMENT_WHITELISTED_IPS', [])
        
        # Allow localhost in development
        if settings.DEBUG and ip in ['127.0.0.1', '::1']:
            return True
        
        return ip in whitelisted_ips


class PaymentValidator:
    """Comprehensive payment data validation"""
    
    @staticmethod
    def validate_payment_amount(amount: Decimal) -> tuple[bool, Optional[str]]:
        """Validate payment amounts with strict rules"""
        if not isinstance(amount, Decimal):
            return False, "Amount must be a decimal"
        
        if amount <= 0:
            return False, "Amount must be positive"
        
        if amount > Decimal('50000.00'):
            return False, "Amount exceeds maximum limit ($50,000)"
        
        if amount.as_tuple().exponent < -2:
            return False, "Amount cannot have more than 2 decimal places"
        
        return True, None
    
    @staticmethod
    def validate_currency(currency: str) -> tuple[bool, Optional[str]]:
        """Validate currency codes"""
        allowed_currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD']
        
        if not currency or len(currency) != 3:
            return False, "Invalid currency format"
        
        if currency.upper() not in allowed_currencies:
            return False, f"Currency {currency} not supported"
        
        return True, None
    
    @staticmethod
    def validate_order_consistency(order, payment_amount: Decimal) -> tuple[bool, Optional[str]]:
        """Validate payment amount matches order total"""
        if abs(order.total_amount - payment_amount) > Decimal('0.01'):
            return False, "Payment amount does not match order total"
        
        if order.status not in ['pending', 'confirmed']:
            return False, "Order is not in a payable state"
        
        return True, None
    
    @staticmethod
    def validate_refund_eligibility(payment, refund_amount: Decimal) -> tuple[bool, Optional[str]]:
        """Validate refund request eligibility"""
        if payment.status != 'succeeded':
            return False, "Payment must be successful to refund"
        
        if refund_amount > payment.amount:
            return False, "Refund amount cannot exceed original payment"
        
        # Check for existing refunds
        existing_refunds = payment.refund_requests.filter(
            status__in=['approved', 'processing', 'completed']
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        
        if existing_refunds + refund_amount > payment.amount:
            return False, "Total refunds would exceed original payment"
        
        return True, None


class StripeSecurityUtils:
    """Security utilities for Stripe integration"""
    
    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
        """Verify Stripe webhook signature"""
        try:
            import stripe
            stripe.Webhook.construct_event(payload, signature, secret)
            return True
        except (ValueError, stripe.error.SignatureVerificationError):
            return False
    
    @staticmethod
    def sanitize_stripe_metadata(metadata: dict) -> dict:
        """Sanitize metadata before sending to Stripe"""
        # Remove sensitive fields
        sensitive_keys = ['password', 'ssn', 'credit_card', 'bank_account']
        
        sanitized = {}
        for key, value in metadata.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                continue
            
            # Limit key and value lengths
            if len(key) > 40 or len(str(value)) > 500:
                continue
            
            sanitized[key] = str(value)
        
        return sanitized
    
    @staticmethod
    def generate_idempotency_key(user_id: str, order_id: str, timestamp: int = None) -> str:
        """Generate idempotency key for Stripe operations"""
        if timestamp is None:
            timestamp = int(time.time())
        
        data = f"{user_id}:{order_id}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]


class PaymentAuditLogger:
    """Comprehensive audit logging for payment operations"""
    
    @staticmethod
    def log_payment_attempt(user_id, order_id, amount, ip_address, user_agent):
        """Log payment processing attempt"""
        logger.info(
            "Payment attempt",
            extra={
                'user_id': user_id,
                'order_id': order_id,
                'amount': str(amount),
                'ip_address': ip_address,
                'user_agent': user_agent,
                'event_type': 'payment_attempt'
            }
        )
    
    @staticmethod
    def log_payment_success(payment_id, user_id, order_id, amount, payment_intent_id):
        """Log successful payment"""
        logger.info(
            "Payment successful",
            extra={
                'payment_id': payment_id,
                'user_id': user_id,
                'order_id': order_id,
                'amount': str(amount),
                'payment_intent_id': payment_intent_id,
                'event_type': 'payment_success'
            }
        )
    
    @staticmethod
    def log_payment_failure(user_id, order_id, amount, error_message, stripe_error_code=None):
        """Log failed payment"""
        logger.warning(
            "Payment failed",
            extra={
                'user_id': user_id,
                'order_id': order_id,
                'amount': str(amount),
                'error_message': error_message,
                'stripe_error_code': stripe_error_code,
                'event_type': 'payment_failure'
            }
        )
    
    @staticmethod
    def log_hold_release(payment_id, amount, seller_count):
        """Log payment hold release"""
        logger.info(
            "Payment hold released",
            extra={
                'payment_id': payment_id,
                'amount': str(amount),
                'seller_count': seller_count,
                'event_type': 'hold_release'
            }
        )
    
    @staticmethod
    def log_security_event(event_type, ip_address, user_id=None, details=None):
        """Log security-related events"""
        logger.warning(
            f"Security event: {event_type}",
            extra={
                'event_type': f'security_{event_type}',
                'ip_address': ip_address,
                'user_id': user_id,
                'details': details
            }
        )


class PaymentEncryption:
    """Encryption utilities for sensitive payment data"""
    
    @staticmethod
    def encrypt_sensitive_data(data: str) -> str:
        """Encrypt sensitive data using Django's SECRET_KEY"""
        from django.core.signing import Signer
        signer = Signer()
        return signer.sign(data)
    
    @staticmethod
    def decrypt_sensitive_data(encrypted_data: str) -> Optional[str]:
        """Decrypt sensitive data"""
        from django.core.signing import Signer, BadSignature
        try:
            signer = Signer()
            return signer.unsign(encrypted_data)
        except BadSignature:
            return None
    
    @staticmethod
    def hash_payment_data(data: str) -> str:
        """Create hash for payment data verification"""
        return hashlib.sha256(
            (data + settings.SECRET_KEY).encode()
        ).hexdigest()


class PaymentRiskAssessment:
    """Risk assessment for payment processing"""
    
    @staticmethod
    def assess_payment_risk(user, order, ip_address) -> tuple[str, float, list]:
        """Assess risk level for payment processing"""
        risk_factors = []
        risk_score = 0.0
        
        # User account age
        account_age_days = (timezone.now() - user.date_joined).days
        if account_age_days < 1:
            risk_score += 0.3
            risk_factors.append("Very new account")
        elif account_age_days < 7:
            risk_score += 0.1
            risk_factors.append("New account")
        
        # Order amount compared to user history
        user_avg_order = user.orders.aggregate(
            avg_amount=models.Avg('total_amount')
        )['avg_amount'] or Decimal('0')
        
        if user_avg_order > 0 and order.total_amount > user_avg_order * 3:
            risk_score += 0.2
            risk_factors.append("Unusually high order amount")
        
        # High-value transaction
        if order.total_amount > Decimal('1000.00'):
            risk_score += 0.1
            risk_factors.append("High-value transaction")
        
        # Multiple payment attempts
        recent_attempts = cache.get(f"payment_attempts_{user.id}", 0)
        if recent_attempts > 3:
            risk_score += 0.2
            risk_factors.append("Multiple recent payment attempts")
        
        # Risk level determination
        if risk_score >= 0.7:
            risk_level = "HIGH"
        elif risk_score >= 0.4:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        return risk_level, risk_score, risk_factors
    
    @staticmethod
    def should_require_additional_verification(risk_level: str, risk_score: float) -> bool:
        """Determine if additional verification is required"""
        return risk_level == "HIGH" or risk_score >= 0.6


# Security configuration constants
SECURITY_SETTINGS = {
    'MAX_PAYMENT_ATTEMPTS_PER_HOUR': 10,
    'MAX_ACCOUNT_CREATION_ATTEMPTS_PER_DAY': 5,
    'PAYMENT_AMOUNT_LIMITS': {
        'min': Decimal('0.50'),
        'max': Decimal('50000.00')
    },
    'ALLOWED_CURRENCIES': ['USD', 'EUR', 'GBP', 'CAD', 'AUD'],
    'WEBHOOK_TIMEOUT_SECONDS': 30,
    'AUDIT_LOG_RETENTION_DAYS': 2555,  # 7 years
    'ENCRYPTED_FIELDS': [
        'payment_method_details',
        'bank_account_last4',
        'routing_number_masked'
    ]
}