"""An email sender that writes to the log instead of the network.

The default, and the counterpart to the fake flight provider. It exists so the
whole system runs and is demonstrable with no mail account, no credentials and
no risk of sending a real message to a real person while developing — which is
the failure mode that makes people afraid to touch email code at all.

The full text body is logged, so what would have been sent is reviewable rather
than merely counted.
"""

from __future__ import annotations

import logging

from app.email.base import EmailMessage

logger = logging.getLogger("flight_system.email")


class ConsoleEmailSender:
    """Writes messages to the log. Satisfies `EmailSender`."""

    name = "console"

    def send(self, message: EmailMessage) -> bool:
        # Attachments are named, never dumped: a megabyte of base64 in a
        # terminal is how you lose the log you were reading.
        files = (
            "  files:   "
            + ", ".join(
                f"{a.filename} ({a.size_bytes / 1024:.0f} KB)"
                for a in message.attachments
            )
            + "\n"
            if message.attachments
            else ""
        )
        logger.info(
            "email (not sent — console sender)\n"
            "  to:      %s\n"
            "  subject: %s\n"
            "%s%s",
            message.to,
            message.subject,
            files,
            _indent(message.text),
        )
        return True


def _indent(body: str) -> str:
    return "\n".join(f"  | {line}" for line in body.strip().splitlines())
