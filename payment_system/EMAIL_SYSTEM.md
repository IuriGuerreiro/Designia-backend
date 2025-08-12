# Email Receipt System for Designia Payment System

## Overview

This email system automatically sends receipt emails to customers when they make purchases, similar to the 2FA email implementation in the authentication system. It includes order receipts, status updates, and cancellation notifications.

## Features

### 📧 Email Types

1. **Order Receipt** - Sent when payment is confirmed
2. **Order Status Updates** - Sent for important status changes (shipped, delivered)
3. **Order Cancellations** - Sent when orders are cancelled with refunds

### 🔒 Security & Rate Limiting

- **Rate Limiting**: Prevents email spam using existing authentication rate limiting system
  - Order receipts: 5-minute cooldown
  - Status updates: 5-minute cooldown  
  - Cancellations: 5-minute cooldown
- **Error Handling**: Graceful fallbacks that don't break order processing
- **Development Mode**: Console output for testing (EMAIL_BACKEND=console)

### 🎨 Templates

- **HTML Template**: Rich, responsive email design with order details
- **Text Template**: Plain text fallback for all email clients
- **Mobile Responsive**: Optimized for mobile devices

## File Structure

```
payment_system/
├── email_utils.py                     # Core email sending functions
├── templates/payment_system/emails/
│   ├── order_receipt.html             # HTML email template
│   └── order_receipt.txt              # Text email template
├── management/commands/
│   └── test_receipt_email.py          # Testing command
└── views.py                           # Integration with webhooks
```

## Email Templates

### HTML Template Features
- Responsive design with mobile-first approach
- Order summary with product images
- Pricing breakdown with taxes and shipping
- Shipping address display
- Call-to-action buttons
- Professional branding

### Text Template Features
- Clean, readable plain text format
- All essential order information
- Fallback for email clients that don't support HTML

## Integration Points

### 1. Order Completion (Webhook)
```python
# In handle_successful_payment()
email_sent, email_message = send_order_receipt_email(order)
```

### 2. Order Cancellation (Webhook)
```python
# In refund.updated webhook handler
email_sent, email_message = send_order_cancellation_receipt_email(
    order, cancellation_reason, refund_amount
)
```

### 3. Status Updates (Manual/Automatic)
```python
# When order status changes
email_sent, email_message = send_order_status_update_email(
    order, previous_status, new_status
)
```

## Email Functions

### `send_order_receipt_email(order, request=None)`
Sends a complete order receipt with all purchase details.

**Parameters:**
- `order`: Order object from marketplace.models
- `request`: Optional HTTP request object for IP logging

**Returns:**
- `(bool, str)`: (success, message)

### `send_order_status_update_email(order, previous_status, new_status, request=None)`
Sends notification when order status changes to important states.

**Parameters:**
- `order`: Order object
- `previous_status`: Previous order status
- `new_status`: New order status
- `request`: Optional HTTP request object

**Returns:**
- `(bool, str)`: (success, message)

### `send_order_cancellation_receipt_email(order, cancellation_reason, refund_amount=None, request=None)`
Sends cancellation confirmation with refund details.

**Parameters:**
- `order`: Order object
- `cancellation_reason`: Reason for cancellation
- `refund_amount`: Refund amount (optional)
- `request`: Optional HTTP request object

**Returns:**
- `(bool, str)`: (success, message)

## Configuration

### Environment Variables
```env
# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend  # Development
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend     # Production
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@designia.com

# Frontend URL for email links
FRONTEND_URL=http://localhost:5173
```

### Django Settings
The system uses existing Django email configuration in `settings.py`:

```python
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@designia.com')
```

## Testing

### Management Command
```bash
# Test with latest order
python manage.py test_receipt_email

# Test with specific order
python manage.py test_receipt_email order-uuid-here

# Test different email types
python manage.py test_receipt_email --type receipt
python manage.py test_receipt_email --type status_update --new-status shipped
python manage.py test_receipt_email --type cancellation --reason "Customer request"
```

### Development Mode
In development (console backend), emails are printed to the console with formatted output:

```
================================================================================
📧 ORDER RECEIPT EMAIL
================================================================================
📧 To: customer@example.com
👤 Customer: John Doe
🛒 Order: #a1b2c3d4
💰 Total: $29.98
📦 Items: 2
📅 Date: 2024-01-15 10:30:00
================================================================================
```

### Rate Limiting Test
```python
# Rate limiting prevents spam - second call within 5 minutes returns:
# (False, "Please wait 287 seconds before requesting another receipt email.")
```

## Production Deployment

### 1. Email Service Setup
Configure SMTP service (Gmail, SendGrid, AWS SES, etc.)

### 2. Environment Variables
Update `.env` file with production email settings:
```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST_USER=noreply@designia.com
EMAIL_HOST_PASSWORD=your-smtp-password
DEFAULT_FROM_EMAIL=noreply@designia.com
FRONTEND_URL=https://designia.com
```

### 3. DNS Configuration
Set up SPF, DKIM, and DMARC records for better deliverability.

### 4. Monitoring
Monitor email delivery rates and bounce rates in your email service dashboard.

## Error Handling

### Graceful Failures
Email failures don't break order processing:
```python
try:
    email_sent, email_message = send_order_receipt_email(order)
    if email_sent:
        print(f"📧 Order receipt email sent to {user.email}")
    else:
        print(f"⚠️ Failed to send receipt email: {email_message}")
except Exception as email_error:
    print(f"❌ Error sending receipt email: {str(email_error)}")
    # Order processing continues normally
```

### Rate Limiting
Built-in rate limiting prevents abuse:
- Uses existing `EmailRequestAttempt` model
- Configurable cooldown periods
- IP address tracking for additional security

### Email Service Failures
- Automatic fallback to text-only emails
- Retry logic for temporary failures
- Detailed error logging for debugging

## Customization

### Adding New Email Types
1. Add new request type to `authentication/models.py`:
```python
('new_email_type', 'New Email Type'),
```

2. Create email function in `email_utils.py`
3. Add templates in `templates/payment_system/emails/`
4. Integrate into appropriate views/webhooks

### Template Customization
- Modify HTML/CSS in `order_receipt.html`
- Update text version in `order_receipt.txt`
- Add company branding and styling
- Include additional order information

### Rate Limiting Customization
Modify cooldown periods in `email_utils.py`:
```python
# Change from 5 minutes to 10 minutes
ten_minutes_ago = timezone.now() - timedelta(minutes=10)
```

## Security Considerations

### Data Protection
- No sensitive payment data in emails
- Order IDs are truncated for security
- IP address logging for audit trails

### Spam Prevention
- Rate limiting prevents automated abuse
- User-specific cooldowns
- Request type separation

### Email Security
- HTML email sanitization
- No executable content in emails
- Safe handling of user data

## Future Enhancements

### Planned Features
- Email tracking and analytics
- Customizable email templates per user
- Multi-language email support
- Email preferences management
- Scheduled email campaigns

### Integration Opportunities
- Push notifications alongside emails
- SMS notifications for critical updates
- Integration with customer support systems
- Advanced personalization based on purchase history

## Troubleshooting

### Common Issues

1. **Emails not sending in development**
   - Check EMAIL_BACKEND setting
   - Verify console output for development mode

2. **Rate limiting too aggressive**
   - Adjust cooldown periods in email_utils.py
   - Check EmailRequestAttempt records in admin

3. **Template rendering errors**
   - Verify template file paths
   - Check template syntax
   - Ensure all context variables are available

4. **Production email failures**
   - Verify SMTP credentials
   - Check DNS records (SPF, DKIM)
   - Monitor email service logs

### Debug Commands
```bash
# Check latest email attempts
python manage.py shell
>>> from authentication.models import EmailRequestAttempt
>>> EmailRequestAttempt.objects.order_by('-created_at')[:5]

# Test email configuration
python manage.py sendtestemail admin@example.com
```

## Support

For issues or questions about the email system:
1. Check console logs for detailed error messages
2. Use the management command for testing
3. Verify email configuration in Django settings
4. Review rate limiting in EmailRequestAttempt model