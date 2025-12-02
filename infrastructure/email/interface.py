"""
Email Service Interface
========================

Abstract base class defining the contract for email operations.
Implements the Interface Segregation Principle.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EmailMessage:
    """
    Represents an email message.

    Attributes:
        subject: Email subject line
        body: Email body (plain text)
        to: List of recipient email addresses
        from_email: Sender email address (optional, uses default if None)
        cc: List of CC email addresses
        bcc: List of BCC email addresses
        html_body: HTML version of email body (optional)
        attachments: List of file paths to attach
    """

    subject: str
    body: str
    to: List[str]
    from_email: Optional[str] = None
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    html_body: Optional[str] = None
    attachments: List[str] = field(default_factory=list)


class EmailServiceInterface(ABC):
    """
    Abstract interface for email operations.

    Concrete implementations:
        - SMTPEmailService: Production email using Django's email backend
        - MockEmailService: Testing email service that logs instead of sending
    """

    @abstractmethod
    def send(self, message: EmailMessage) -> bool:
        """
        Send a single email message.

        Args:
            message: EmailMessage to send

        Returns:
            True if email sent successfully, False otherwise

        Raises:
            EmailException: If sending fails critically
        """
        pass

    @abstractmethod
    def send_bulk(self, messages: List[EmailMessage]) -> int:
        """
        Send multiple email messages efficiently.

        Args:
            messages: List of EmailMessage objects to send

        Returns:
            Number of emails sent successfully

        Raises:
            EmailException: If bulk send fails critically
        """
        pass

    @abstractmethod
    def send_html(
        self,
        subject: str,
        html_content: str,
        to: List[str],
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Send an HTML email.

        Args:
            subject: Email subject
            html_content: HTML body content
            to: List of recipient addresses
            from_email: Sender address (uses default if None)

        Returns:
            True if sent successfully, False otherwise

        Raises:
            EmailException: If sending fails
        """
        pass


class EmailException(Exception):
    """Base exception for email operations."""

    pass
