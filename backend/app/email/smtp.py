"""SMTP.

Deliberately SMTP rather than a provider's SDK. Every mail service worth using
speaks it — Postmark, SendGrid, SES, Mailgun, Resend, a self-hosted Postfix —
so switching provider is four environment variables rather than a new
dependency and a rewrite. `smtplib` is in the standard library, so this costs
nothing to carry.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

from app.email.base import EmailError, EmailMessage

logger = logging.getLogger("flight_system.email")

# Short on purpose. This runs in a background task, but a background task that
# hangs for two minutes still holds a worker, and a mail server that has not
# answered in ten seconds is not about to.
DEFAULT_TIMEOUT = 10.0


class SmtpEmailSender:
    """Sends through an SMTP server. Satisfies `EmailSender`."""

    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        sender: str,
        use_starttls: bool = True,
        use_ssl: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not host.strip():
            # Fail at construction, not at send time. A missing host is a
            # deployment mistake, and finding it when the process starts is far
            # cheaper than finding it in a log after a customer did not get
            # their confirmation.
            raise EmailError(
                "email_sender=smtp but SMTP_HOST is not set. Set it, or use "
                "EMAIL_SENDER=console to run without a mail server."
            )
        if not sender.strip():
            raise EmailError("EMAIL_FROM is not set; every message needs a From.")

        self._host = host.strip()
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender.strip()
        self._use_starttls = use_starttls
        self._use_ssl = use_ssl
        self._timeout = timeout

    def send(self, message: EmailMessage) -> bool:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        if message.reply_to:
            mime["Reply-To"] = message.reply_to

        # Text first, then HTML. The order is the standard: a client that
        # understands multipart/alternative shows the last part it can render,
        # and one that does not shows the first.
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")

        for attachment in message.attachments:
            main, _, sub = attachment.content_type.partition("/")
            mime.add_attachment(
                attachment.content,
                maintype=main or "application",
                subtype=sub or "octet-stream",
                filename=attachment.filename,
            )

        try:
            with self._connect() as server:
                if self._username:
                    server.login(self._username, self._password)
                server.send_message(mime)
        except (smtplib.SMTPException, OSError) as exc:
            # Never raised onward. The claim is already stored and the customer
            # is already looking at their reference; failing now would tell them
            # something went wrong with the thing that actually worked.
            logger.error(
                "could not send email to %s (%s): %s",
                message.to,
                type(exc).__name__,
                exc,
            )
            return False

        logger.info("sent email to %s: %s", message.to, message.subject)
        return True

    def _connect(self) -> smtplib.SMTP:
        if self._use_ssl:
            return smtplib.SMTP_SSL(
                self._host, self._port, timeout=self._timeout,
                context=ssl.create_default_context(),
            )
        server = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        if self._use_starttls:
            server.starttls(context=ssl.create_default_context())
        return server
