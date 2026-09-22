"""Selecting an email sender by name.

The single place that knows which adapters exist, so changing how mail is sent
is a configuration change rather than a code change.
"""

from __future__ import annotations

from app.email.base import EmailSender
from app.email.console import ConsoleEmailSender
from app.email.resend import ResendEmailSender
from app.email.smtp import SmtpEmailSender

CONSOLE = "console"
SMTP = "smtp"
RESEND = "resend"

AVAILABLE: tuple[str, ...] = (CONSOLE, SMTP, RESEND)


def build_email_sender(name: str, settings: object) -> EmailSender:
    """Construct the named sender from settings.

    Raises ValueError for an unknown name -- a misconfigured sender is a
    deployment mistake that should stop the application at startup rather than
    turn into silently unsent mail.
    """
    chosen = name.strip().lower()

    if chosen == CONSOLE:
        return ConsoleEmailSender()

    if chosen == SMTP:
        return SmtpEmailSender(
            host=getattr(settings, "smtp_host", ""),
            port=getattr(settings, "smtp_port", 587),
            username=getattr(settings, "smtp_username", ""),
            password=getattr(settings, "smtp_password", ""),
            sender=getattr(settings, "email_from", ""),
            use_starttls=getattr(settings, "smtp_starttls", True),
            use_ssl=getattr(settings, "smtp_ssl", False),
        )

    if chosen == RESEND:
        return ResendEmailSender(
            api_key=getattr(settings, "resend_api_key", ""),
            sender=getattr(settings, "email_from", ""),
        )

    raise ValueError(
        f"unknown email sender {name!r}; available: {', '.join(AVAILABLE)}"
    )
