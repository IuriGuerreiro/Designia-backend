# Payment System Security Configuration

## Security Architecture Overview

The payment system implements multiple layers of security to protect financial transactions and sensitive data.

## Security Middleware Configuration

### PaymentSecurityMiddleware

Add to Django settings:

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'payment_system.security.PaymentSecurityMiddleware',  # Add this
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Payment security settings
PAYMENT_WHITELISTED_IPS = [
    '192.168.1.100',  # Office IP
    '10.0.0.1',       # VPN Gateway
    # Add your production IPs
]

# Rate limiting cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

### Security Features

#### 1. Rate Limiting
- **Payment Processing**: 10 attempts per minute per IP
- **Account Creation**: 5 attempts per hour per IP  
- **General Endpoints**: 100 requests per minute per IP

#### 2. IP Whitelisting
- Sensitive endpoints require IP whitelisting
- Admin endpoints protected by IP restrictions
- Webhook endpoints secured with IP validation

#### 3. Request Validation
- Input sanitization and validation
- Payment amount limits and format validation
- Currency code validation
- Order consistency verification

## Payment Data Validation

### Amount Validation
```python
from payment_system.security import PaymentValidator

# Validate payment amount
is_valid, error = PaymentValidator.validate_payment_amount(amount)
if not is_valid:
    raise ValidationError(error)

# Validate currency
is_valid, error = PaymentValidator.validate_currency('USD')
if not is_valid:
    raise ValidationError(error)
```

### Refund Validation
```python
# Check refund eligibility
is_valid, error = PaymentValidator.validate_refund_eligibility(
    payment, refund_amount
)
if not is_valid:
    raise ValidationError(error)
```

## Stripe Security Integration

### Webhook Signature Verification
```python
from payment_system.security import StripeSecurityUtils

# Verify webhook signature
is_valid = StripeSecurityUtils.verify_webhook_signature(
    payload, signature, webhook_secret
)
if not is_valid:
    return HttpResponse(status=400)
```

### Metadata Sanitization
```python
# Sanitize metadata before sending to Stripe
clean_metadata = StripeSecurityUtils.sanitize_stripe_metadata({
    'order_id': order.id,
    'user_id': user.id,
    'sensitive_data': 'removed_automatically'  # This will be filtered out
})
```

### Idempotency Keys
```python
# Generate secure idempotency key
idempotency_key = StripeSecurityUtils.generate_idempotency_key(
    user_id=str(user.id),
    order_id=str(order.id)
)
```

## Audit Logging

### Comprehensive Event Logging
```python
from payment_system.security import PaymentAuditLogger

# Log payment attempt
PaymentAuditLogger.log_payment_attempt(
    user_id=user.id,
    order_id=order.id,
    amount=payment_amount,
    ip_address=get_client_ip(request),
    user_agent=request.META.get('HTTP_USER_AGENT')
)

# Log security events
PaymentAuditLogger.log_security_event(
    event_type='rate_limit_exceeded',
    ip_address=client_ip,
    details={'endpoint': request.path}
)
```

### Log Analysis
All payment events are logged with structured data for analysis:

```json
{
    "timestamp": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "event_type": "payment_success",
    "payment_id": "12345678-1234-1234-1234-123456789012",
    "user_id": "user_123",
    "amount": "99.99",
    "ip_address": "192.168.1.100"
}
```

## Data Encryption

### Sensitive Data Protection
```python
from payment_system.security import PaymentEncryption

# Encrypt sensitive payment data
encrypted_data = PaymentEncryption.encrypt_sensitive_data(
    payment_method_details
)

# Decrypt when needed
decrypted_data = PaymentEncryption.decrypt_sensitive_data(encrypted_data)

# Create verification hash
hash_value = PaymentEncryption.hash_payment_data(payment_data)
```

### Encrypted Fields
The following fields are automatically encrypted:
- Payment method details
- Bank account information (last 4 digits)
- Routing numbers (masked)

## Risk Assessment

### Automatic Risk Evaluation
```python
from payment_system.security import PaymentRiskAssessment

# Assess payment risk
risk_level, risk_score, factors = PaymentRiskAssessment.assess_payment_risk(
    user=user,
    order=order,
    ip_address=client_ip
)

# Require additional verification for high-risk payments
if PaymentRiskAssessment.should_require_additional_verification(
    risk_level, risk_score
):
    # Implement additional verification steps
    require_3ds_authentication()
```

### Risk Factors Evaluated
- Account age and history
- Order amount vs. user history
- Recent payment attempt frequency
- Geographic location
- Device fingerprinting
- Time-of-day patterns

## Security Configuration Constants

### Payment Limits
```python
SECURITY_SETTINGS = {
    'MAX_PAYMENT_ATTEMPTS_PER_HOUR': 10,
    'MAX_ACCOUNT_CREATION_ATTEMPTS_PER_DAY': 5,
    'PAYMENT_AMOUNT_LIMITS': {
        'min': Decimal('0.50'),
        'max': Decimal('50000.00')
    },
    'ALLOWED_CURRENCIES': ['USD', 'EUR', 'GBP', 'CAD', 'AUD'],
    'AUDIT_LOG_RETENTION_DAYS': 2555,  # 7 years for compliance
}
```

## Production Security Checklist

### Environment Security
- [ ] Stripe production keys configured
- [ ] Webhook secrets properly set
- [ ] IP whitelist configured for production
- [ ] SSL/TLS certificates installed
- [ ] Database encryption enabled
- [ ] Redis cache secured

### Application Security
- [ ] Security middleware enabled
- [ ] Rate limiting configured
- [ ] Audit logging active
- [ ] Error handling implemented
- [ ] Input validation enabled
- [ ] CSRF protection active

### Monitoring & Alerting
- [ ] Failed payment monitoring
- [ ] Unusual activity alerts
- [ ] Rate limit breach notifications
- [ ] Security event alerting
- [ ] Webhook failure monitoring
- [ ] High-risk payment flagging

## Security Incident Response

### Automated Responses
- **Rate Limit Exceeded**: Temporary IP blocking
- **Multiple Failed Payments**: Account temporary suspension
- **Suspicious Activity**: Enhanced verification required
- **Webhook Failures**: Automatic retry with exponential backoff

### Manual Response Procedures
1. **Identify Threat**: Analyze security logs and patterns
2. **Contain Impact**: Block suspicious IPs/accounts
3. **Investigate**: Review transaction history and patterns
4. **Remediate**: Apply fixes and security patches
5. **Monitor**: Enhanced monitoring post-incident

## Compliance Features

### PCI DSS Compliance
- No sensitive card data stored locally
- All payments processed through Stripe
- Encrypted data transmission
- Access controls and authentication
- Regular security monitoring

### Data Protection
- GDPR compliant data handling
- User consent management
- Data retention policies
- Right to deletion support
- Data breach notification procedures

### Financial Regulations
- Anti-money laundering (AML) checks
- Know Your Customer (KYC) verification
- Transaction reporting capabilities
- Audit trail maintenance
- Regulatory reporting support

## Security Testing

### Automated Testing
```python
# test_security.py
class PaymentSecurityTestCase(TestCase):
    def test_rate_limiting(self):
        # Test rate limiting functionality
        pass
    
    def test_input_validation(self):
        # Test input validation
        pass
    
    def test_encryption(self):
        # Test data encryption/decryption
        pass
    
    def test_audit_logging(self):
        # Test audit log creation
        pass
```

### Penetration Testing
- Regular security assessments
- Payment flow vulnerability testing
- API endpoint security testing  
- Authentication bypass testing
- Input validation testing

## Security Monitoring

### Key Metrics
- Failed payment attempts per hour
- Rate limit violations
- High-risk payment percentage
- Webhook processing failures
- Security event frequency

### Dashboard Alerts
- Real-time payment failure monitoring
- Unusual transaction pattern detection
- Geographic anomaly alerts
- High-value transaction notifications
- Security event summaries

This comprehensive security configuration ensures robust protection for the payment system while maintaining usability and performance.