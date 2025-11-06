import logging
from typing import Iterable, Optional, Tuple

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_email(
    subject: str,
    message: str,
    recipient_list: Iterable[str],
    *,
    from_email: Optional[str] = None,
    html_message: Optional[str] = None,
    fail_silently: bool = False,
) -> Tuple[bool, str]:
    """
    Send an email using Django settings. If the configured backend is console
    or sending fails, print a readable fallback to stdout and return status.

    Returns (success, info_message).
    """
    from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")

    # If console backend, log the email in a friendly format
    if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
        _print_email_fallback(subject, message, recipient_list, html_message)
        return True, "Email printed to console (development backend)"

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=list(recipient_list),
            fail_silently=False,
            html_message=html_message,
        )
        if sent_count > 0:
            return True, "Email sent successfully"
        return False, "Email backend returned 0 sent"
    except Exception as e:
        # Fallback to logging for visibility in non-console backends on error
        _print_email_fallback(subject, message, recipient_list, html_message, error=str(e))
        if fail_silently:
            return False, "Email send failed (silenced)"
        return False, f"Email send failed: {e}"


def _print_email_fallback(
    subject: str,
    message: str,
    recipient_list: Iterable[str],
    html_message: Optional[str] = None,
    *,
    error: Optional[str] = None,
) -> None:
    header = "\n" + "=" * 80
    footer = "=" * 80 + "\n"
    lines = [
        header,
        "⚠️  EMAIL SEND FAILED — FALLBACK OUTPUT" if error else "✉️  EMAIL (CONSOLE BACKEND)",
        "=" * 80,
        f"To: {', '.join(recipient_list)}",
        f"Subject: {subject}",
        "-" * 80,
    ]
    if html_message:
        lines.append("(HTML content below)")
        lines.append(str(html_message))
        lines.append("-" * 80)
    lines.append(str(message))
    lines.append(footer)

    log_msg = "\n".join(lines)
    if error:
        logger.error(log_msg)
    else:
        logger.info(log_msg)
