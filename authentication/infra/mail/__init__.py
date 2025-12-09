"""
Email infrastructure abstractions.

Provides EmailProvider interface and implementations.
"""

from .django_email_provider import DjangoEmailProvider
from .email_interface import EmailProvider
from .mock_email_provider import MockEmailProvider

__all__ = ["EmailProvider", "DjangoEmailProvider", "MockEmailProvider"]
