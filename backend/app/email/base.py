"""The port: what the rest of the system requires of an email sender.

Same shape as the flight-data port, for the same reason. Mail providers get
switched — a free tier runs out, deliverability goes bad, somebody moves to SES
— and a system welded to one vendor's SDK makes that a rewrite. Nothing above
this layer imports a provider or knows how mail is actually sent.

    app/email/
        base.py      this file: the message, the contract, the failures
        console.py   adapter: writes to the log, needs no configuration
        smtp.py      adapter: any SMTP provider
        messages.py  the emails themselves — subject, text and HTML
        registry.py  pick one by name

THE RULE THAT MATTERS MOST
--------------------------
**A failed email must never fail the thing it was reporting on.** A customer
who submits a claim and sees an error because our mail server is down will
assume the claim did not go through, and will either give up or submit it
again. The claim is the valuable thing; the email is a courtesy. So every
send is fire-and-forget, failures are logged rather than raised, and callers
are given no way to make the outcome depend on them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    """A file travelling with an email.

    WHY THE BYTES AND NOT A LINK
    ----------------------------
    A link needs somewhere durable to point at, and an authenticated way to
    reach it. Uploads currently live on the container's own disk, which on a
    managed host does NOT survive a deploy -- so a link in an inbox would rot
    quietly, and the email would become a promise the system cannot keep.

    Attaching the bytes makes the message self-contained: whoever opens it
    sees the receipt, today and in a year, whatever happened to the disk.

    It is also the only form that answers the actual question. "IMG_5992.jpg"
    tells somebody chasing an airline nothing at all; the photograph of the
    receipt is the evidence.
    """

    filename: str
    content: bytes
    content_type: str

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("an attachment needs a filename")
        if not self.content:
            raise ValueError(f"attachment {self.filename!r} is empty")

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """One email, in both forms.

    Both `text` and `html` are required rather than optional. A plain-text part
    is not a legacy courtesy: it is what spam filters score, what screen
    readers prefer, and what renders when a client blocks HTML. Making it
    optional means it gets skipped, and then the mail lands in spam for a
    reason nobody can find.
    """

    to: str
    subject: str
    text: str
    html: str
    reply_to: str | None = None
    # A tuple rather than a list, because the message is frozen and a mutable
    # default on a shared dataclass is the oldest bug in Python.
    attachments: tuple[EmailAttachment, ...] = ()

    def __post_init__(self) -> None:
        if not self.to.strip() or "@" not in self.to:
            raise ValueError(f"not an email address: {self.to!r}")
        if not self.subject.strip():
            raise ValueError("an email needs a subject")
        if not self.text.strip() or not self.html.strip():
            raise ValueError("an email needs both a text and an HTML body")


@runtime_checkable
class EmailSender(Protocol):
    """The contract every mail adapter satisfies."""

    name: str

    def send(self, message: EmailMessage) -> bool:
        """Send one message. Returns whether it went.

        Returns a bool rather than raising, because the caller is never in a
        position to do anything useful with an exception: the claim is already
        stored and the customer is already looking at the confirmation. The
        answer is for logging and for the one place that genuinely cares --
        deciding whether to record the send.
        """
        ...


class EmailError(Exception):
    """Raised only by configuration, never by sending.

    A missing SMTP host is a deployment mistake that should stop the process at
    startup. A refused connection at send time is not: it is logged and the
    request carries on.
    """
