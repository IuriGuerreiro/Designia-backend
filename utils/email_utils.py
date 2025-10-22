import sys
from typing import Iterable, Optional, Tuple

from django.conf import settings
from django.core.mail import send_mail


def send_email(subject: str,
               message: str,
               recipient_list: Iterable[str],
               *,
               from_email: Optional[str] = None,
               html_message: Optional[str] = None,
               fail_silently: bool = False) -> Tuple[bool, str]:
    """
    Send an email using Django settings. If the configured backend is console
    or sending fails, print a readable fallback to stdout and return status.

    Returns (success, info_message).
    """
    from_email = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost')

    # If console backend, just print the email in a friendly format
    if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
        _print_email_fallback(subject, message, recipient_list, html_message)
        return True, 'Email printed to console (development backend)'

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
            return True, 'Email sent successfully'
        return False, 'Email backend returned 0 sent'
    except Exception as e:
        # Fallback to printing for visibility in non-console backends on error
        _print_email_fallback(subject, message, recipient_list, html_message, error=str(e))
        if fail_silently:
            return False, 'Email send failed (silenced)'
        return False, f'Email send failed: {e}'


def _print_email_fallback(subject: str,
                          message: str,
                          recipient_list: Iterable[str],
                          html_message: Optional[str] = None,
                          *,
                          error: Optional[str] = None) -> None:
    print('\n' + '=' * 80, file=sys.stdout)
    if error:
        print('⚠️  EMAIL SEND FAILED — FALLBACK OUTPUT', file=sys.stdout)
        print(f'Error: {error}', file=sys.stdout)
    else:
        print('✉️  EMAIL (CONSOLE BACKEND)', file=sys.stdout)
    print('=' * 80, file=sys.stdout)
    print(f'To: {", ".join(recipient_list)}', file=sys.stdout)
    print(f'Subject: {subject}', file=sys.stdout)
    print('-' * 80, file=sys.stdout)
    if html_message:
        print('(HTML content below)', file=sys.stdout)
        print(html_message, file=sys.stdout)
        print('-' * 80, file=sys.stdout)
    print(message, file=sys.stdout)
    print('=' * 80 + '\n', file=sys.stdout)

