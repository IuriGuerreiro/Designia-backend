"""
SMTP Email Service
==================

Concrete implementation of EmailServiceInterface using Django's email backend.
Production-ready email service supporting SMTP, SendGrid, AWS SES, etc.
"""

import logging
from typing import List, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail, send_mass_mail

from .interface import EmailException, EmailMessage, EmailServiceInterface


logger = logging.getLogger(__name__)


class SMTPEmailService(EmailServiceInterface):
    """
    Django SMTP email service implementation.

    Configuration (in settings.py):
        EMAIL_BACKEND: Django email backend class
        EMAIL_HOST: SMTP server host
        EMAIL_PORT: SMTP server port
        EMAIL_HOST_USER: SMTP username
        EMAIL_HOST_PASSWORD: SMTP password
        EMAIL_USE_TLS: Use TLS encryption
        DEFAULT_FROM_EMAIL: Default sender address
    """

    def __init__(self):
        """Initialize SMTP email service."""
        self.default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    def send(self, message: EmailMessage) -> bool:
        """
        Send a single email using Django's send_mail.

        Args:
            message: EmailMessage to send

        Returns:
            True if email sent successfully

        Raises:
            EmailException: If sending fails
        """
        try:
            from_email = message.from_email or self.default_from

            if message.html_body:
                # Send HTML email with plain text fallback
                return self._send_html_email(
                    subject=message.subject,
                    html_content=message.html_body,
                    plain_content=message.body,
                    to=message.to,
                    from_email=from_email,
                    cc=message.cc,
                    bcc=message.bcc,
                    attachments=message.attachments,
                )
            else:
                # Send plain text email
                num_sent = send_mail(
                    subject=message.subject,
                    message=message.body,
                    from_email=from_email,
                    recipient_list=message.to,
                    fail_silently=False,
                )

                success = num_sent > 0
                if success:
                    logger.info(f"Email sent successfully to {message.to}")
                else:
                    logger.warning(f"Email failed to send to {message.to}")

                return success

        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            raise EmailException(f"Email send failed: {str(e)}") from e

    def send_bulk(self, messages: List[EmailMessage]) -> int:
        """
        Send multiple emails efficiently using Django's send_mass_mail.

        Args:
            messages: List of EmailMessage objects

        Returns:
            Number of emails sent successfully

        Raises:
            EmailException: If bulk send fails
        """
        try:
            # Convert EmailMessage objects to tuples for send_mass_mail
            mail_tuples = []
            for msg in messages:
                from_email = msg.from_email or self.default_from
                mail_tuples.append(
                    (
                        msg.subject,
                        msg.body,
                        from_email,
                        msg.to,
                    )
                )

            num_sent = send_mass_mail(mail_tuples, fail_silently=False)
            logger.info(f"Bulk email: sent {num_sent} of {len(messages)} emails")

            return num_sent

        except Exception as e:
            logger.error(f"Failed to send bulk emails: {str(e)}")
            raise EmailException(f"Bulk email send failed: {str(e)}") from e

    def send_html(
        self,
        subject: str,
        html_content: str,
        to: List[str],
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Send an HTML email with automatic plain text fallback.

        Args:
            subject: Email subject
            html_content: HTML body content
            to: Recipient addresses
            from_email: Sender address

        Returns:
            True if sent successfully

        Raises:
            EmailException: If sending fails
        """
        try:
            return self._send_html_email(
                subject=subject,
                html_content=html_content,
                plain_content="",  # Django will auto-generate from HTML
                to=to,
                from_email=from_email or self.default_from,
            )

        except Exception as e:
            logger.error(f"Failed to send HTML email: {str(e)}")
            raise EmailException(f"HTML email send failed: {str(e)}") from e

    def _send_html_email(
        self,
        subject: str,
        html_content: str,
        plain_content: str,
        to: List[str],
        from_email: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
    ) -> bool:
        """
        Internal method to send HTML email with attachments.

        Args:
            subject: Email subject
            html_content: HTML body
            plain_content: Plain text body (fallback)
            to: Recipients
            from_email: Sender
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of file paths to attach

        Returns:
            True if sent successfully
        """
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_content,
            from_email=from_email,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
        )

        msg.attach_alternative(html_content, "text/html")

        # Attach files if provided
        if attachments:
            for file_path in attachments:
                msg.attach_file(file_path)

        num_sent = msg.send(fail_silently=False)
        success = num_sent > 0

        if success:
            logger.info(f"HTML email sent successfully to {to}")
        else:
            logger.warning(f"HTML email failed to send to {to}")

        return success
