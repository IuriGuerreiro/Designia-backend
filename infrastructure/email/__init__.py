"""
Email Service Abstraction Layer
================================

Provides a unified interface for email operations across different backends.
"""

from .factory import EmailFactory
from .interface import EmailException, EmailMessage, EmailServiceInterface
from .mock_service import MockEmailService
from .smtp_service import SMTPEmailService

__all__ = [
    "EmailServiceInterface",
    "EmailMessage",
    "EmailException",
    "SMTPEmailService",
    "MockEmailService",
    "EmailFactory",
]
