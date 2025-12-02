"""
Email Infrastructure Tests
===========================

Unit tests for email service abstraction layer.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from infrastructure.email import (
    EmailException,
    EmailFactory,
    EmailMessage,
    EmailServiceInterface,
    MockEmailService,
    SMTPEmailService,
)


class EmailInterfaceTest(TestCase):
    """Test EmailServiceInterface contract."""

    def test_interface_is_abstract(self):
        """EmailServiceInterface should not be instantiable."""
        with self.assertRaises(TypeError):
            EmailServiceInterface()


class MockEmailServiceTest(TestCase):
    """Test MockEmailService implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.email_service = MockEmailService()

    def tearDown(self):
        """Clean up after each test."""
        self.email_service.clear_sent_messages()

    def test_send_email(self):
        """Test sending a single email."""
        message = EmailMessage(
            subject="Test Subject",
            body="Test body content",
            to=["test@example.com"],
            from_email="sender@example.com",
        )

        result = self.email_service.send(message)

        self.assertTrue(result)
        self.assertEqual(self.email_service.get_sent_count(), 1)
        self.assertEqual(self.email_service.get_last_message(), message)

    def test_send_bulk_emails(self):
        """Test sending multiple emails."""
        messages = [
            EmailMessage(
                subject=f"Test {i}",
                body=f"Body {i}",
                to=[f"user{i}@example.com"],
            )
            for i in range(5)
        ]

        count = self.email_service.send_bulk(messages)

        self.assertEqual(count, 5)
        self.assertEqual(self.email_service.get_sent_count(), 5)

    def test_send_html_email(self):
        """Test sending HTML email."""
        result = self.email_service.send_html(
            subject="HTML Test",
            html_content="<h1>Hello World</h1>",
            to=["test@example.com"],
        )

        self.assertTrue(result)
        self.assertEqual(self.email_service.get_sent_count(), 1)

        last_message = self.email_service.get_last_message()
        self.assertEqual(last_message.subject, "HTML Test")
        self.assertEqual(last_message.html_body, "<h1>Hello World</h1>")

    def test_clear_sent_messages(self):
        """Test clearing sent messages."""
        self.email_service.send(EmailMessage(subject="Test", body="Body", to=["test@example.com"]))

        self.assertEqual(self.email_service.get_sent_count(), 1)

        self.email_service.clear_sent_messages()

        self.assertEqual(self.email_service.get_sent_count(), 0)
        self.assertIsNone(self.email_service.get_last_message())

    def test_get_last_message_empty(self):
        """Test getting last message when no messages sent."""
        self.assertIsNone(self.email_service.get_last_message())


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@test.com",
)
class SMTPEmailServiceTest(TestCase):
    """Test SMTPEmailService implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.email_service = SMTPEmailService()

    @patch("infrastructure.email.smtp_service.send_mail")
    def test_send_email_success(self, mock_send_mail):
        """Test successful email send."""
        mock_send_mail.return_value = 1

        message = EmailMessage(
            subject="Test Subject",
            body="Test body",
            to=["test@example.com"],
        )

        result = self.email_service.send(message)

        self.assertTrue(result)
        mock_send_mail.assert_called_once()

    @patch("infrastructure.email.smtp_service.send_mail")
    def test_send_email_failure(self, mock_send_mail):
        """Test email send failure."""
        mock_send_mail.side_effect = Exception("SMTP error")

        message = EmailMessage(
            subject="Test",
            body="Body",
            to=["test@example.com"],
        )

        with self.assertRaises(EmailException):
            self.email_service.send(message)

    @patch("infrastructure.email.smtp_service.send_mass_mail")
    def test_send_bulk_emails(self, mock_send_mass_mail):
        """Test bulk email sending."""
        mock_send_mass_mail.return_value = 3

        messages = [EmailMessage(subject=f"Test {i}", body=f"Body {i}", to=[f"user{i}@test.com"]) for i in range(3)]

        count = self.email_service.send_bulk(messages)

        self.assertEqual(count, 3)
        mock_send_mass_mail.assert_called_once()

    @patch("infrastructure.email.smtp_service.EmailMultiAlternatives")
    def test_send_html_email(self, mock_email_class):
        """Test HTML email sending."""
        mock_msg = MagicMock()
        mock_msg.send.return_value = 1
        mock_email_class.return_value = mock_msg

        result = self.email_service.send_html(
            subject="HTML Test",
            html_content="<h1>Test</h1>",
            to=["test@example.com"],
        )

        self.assertTrue(result)
        mock_msg.attach_alternative.assert_called_once_with("<h1>Test</h1>", "text/html")
        mock_msg.send.assert_called_once()

    def test_default_from_email(self):
        """Test default from email is set from settings."""
        self.assertEqual(self.email_service.default_from, "noreply@test.com")

    @patch("infrastructure.email.smtp_service.EmailMultiAlternatives")
    def test_send_html_with_attachments(self, mock_email_class):
        """Test HTML email with attachments."""
        mock_msg = MagicMock()
        mock_msg.send.return_value = 1
        mock_email_class.return_value = mock_msg

        message = EmailMessage(
            subject="Test",
            body="Body",
            to=["test@example.com"],
            html_body="<h1>HTML</h1>",
            attachments=["path/to/file.pdf"],
        )

        result = self.email_service.send(message)

        self.assertTrue(result)
        mock_msg.attach_file.assert_called_once_with("path/to/file.pdf")


class EmailFactoryTest(TestCase):
    """Test EmailFactory."""

    @override_settings(EMAIL_SERVICE_BACKEND="mock")
    def test_create_mock_service(self):
        """Test factory creates mock service from settings."""
        service = EmailFactory.create()
        self.assertIsInstance(service, MockEmailService)

    @override_settings(EMAIL_SERVICE_BACKEND="smtp")
    def test_create_smtp_service(self):
        """Test factory creates SMTP service from settings."""
        service = EmailFactory.create()
        self.assertIsInstance(service, SMTPEmailService)

    def test_create_with_explicit_backend(self):
        """Test factory with explicit backend."""
        service = EmailFactory.create("mock")
        self.assertIsInstance(service, MockEmailService)

    def test_create_invalid_backend(self):
        """Test factory raises error for invalid backend."""
        with self.assertRaises(ValueError):
            EmailFactory.create("invalid")

    def test_create_smtp_explicit(self):
        """Test explicit SMTP creation."""
        service = EmailFactory.create_smtp()
        self.assertIsInstance(service, SMTPEmailService)

    def test_create_mock_explicit(self):
        """Test explicit mock creation."""
        service = EmailFactory.create_mock()
        self.assertIsInstance(service, MockEmailService)

    @override_settings(TESTING=True)
    def test_default_to_mock_in_testing(self):
        """Test factory defaults to mock in testing mode."""
        service = EmailFactory.create()
        self.assertIsInstance(service, MockEmailService)
