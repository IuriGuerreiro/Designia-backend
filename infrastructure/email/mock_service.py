"""
Mock Email Service
==================

Mock implementation of EmailServiceInterface for testing.
Logs email operations instead of actually sending them.
"""

import logging
from typing import List, Optional

from .interface import EmailMessage, EmailServiceInterface

logger = logging.getLogger(__name__)


class MockEmailService(EmailServiceInterface):
    """
    Mock email service for testing and development.

    Instead of sending emails, this service:
        - Logs all email operations
        - Stores sent messages in memory for verification
        - Always returns success

    Useful for:
        - Unit testing
        - Development environments
        - CI/CD pipelines
    """

    def __init__(self):
        """Initialize mock email service with empty sent messages list."""
        self.sent_messages: List[EmailMessage] = []

    def send(self, message: EmailMessage) -> bool:
        """
        Mock send operation - logs and stores message.

        Args:
            message: EmailMessage to "send"

        Returns:
            Always returns True
        """
        logger.info(
            f"[MOCK EMAIL] To: {message.to}, " f"Subject: {message.subject}, " f"Body: {message.body[:100]}..."
        )

        self.sent_messages.append(message)
        return True

    def send_bulk(self, messages: List[EmailMessage]) -> int:
        """
        Mock bulk send - logs and stores all messages.

        Args:
            messages: List of EmailMessage objects

        Returns:
            Number of messages "sent" (always equals len(messages))
        """
        logger.info(f"[MOCK EMAIL] Bulk send: {len(messages)} emails")

        for message in messages:
            self.send(message)

        return len(messages)

    def send_html(
        self,
        subject: str,
        html_content: str,
        to: List[str],
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Mock HTML email send.

        Args:
            subject: Email subject
            html_content: HTML body
            to: Recipients
            from_email: Sender

        Returns:
            Always returns True
        """
        logger.info(f"[MOCK EMAIL] HTML To: {to}, " f"Subject: {subject}, " f"HTML Length: {len(html_content)} chars")

        # Create EmailMessage and store
        message = EmailMessage(
            subject=subject,
            body="",  # HTML emails may not have plain body
            to=to,
            from_email=from_email,
            html_body=html_content,
        )

        self.sent_messages.append(message)
        return True

    def clear_sent_messages(self):
        """Clear the list of sent messages (useful between tests)."""
        self.sent_messages.clear()
        logger.info("[MOCK EMAIL] Cleared sent messages")

    def get_sent_count(self) -> int:
        """
        Get the number of messages sent.

        Returns:
            Number of messages in sent_messages list
        """
        return len(self.sent_messages)

    def get_last_message(self) -> Optional[EmailMessage]:
        """
        Get the most recently sent message.

        Returns:
            Last EmailMessage or None if no messages sent
        """
        return self.sent_messages[-1] if self.sent_messages else None
