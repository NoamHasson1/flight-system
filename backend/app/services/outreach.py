"""The two emails an operator sends by hand.

Everything else this system sends is automatic: a result, a confirmation,
a copy to the office. These two are different -- a person decided to send
them, about one claim, at a moment of their choosing.

    STATEMENT OF CLAIM    the pleading, going out to the customer
    REQUEST FOR ITEMS     what we still need before we can file

WHY THEY LIVE HERE AND NOT IN THE ROUTE

A route should validate, call, and serialise. The wording of a letter
that goes to a customer over a lawyer's name is not an implementation
detail of an HTTP handler, and it is the part most likely to be edited by
somebody who is not reading Python.

WHY BOTH ARE RECORDED

Sending is not the end of it. "Did we send them the pleading, and when?"
is a question that gets asked months later, usually by somebody who is
not the person who sent it. The statement is stored as a document on the
claim before it goes, so the answer lives in the database rather than in
one person's sent folder.
"""

from __future__ import annotations

import logging

from app.db.models import Claim
from app.email.base import EmailAttachment, EmailMessage, EmailSender

logger = logging.getLogger("flight_system.outreach")

# What an operator can ask for, as a closed list.
#
# Free text would be easier and worse. These are the things that actually
# hold a claim up, they are the same every time, and a fixed list means
# the customer gets a clear checklist instead of a sentence somebody typed
# in a hurry -- and that we can later count which item stalls claims most.
REQUESTABLE: dict[str, str] = {
    "BOOKING": "אישור הזמנה או כרטיס טיסה",
    "BOARDING_PASS": "כרטיס עלייה למטוס",
    "RECEIPTS": "קבלות על ההוצאות שנרשמו",
    "ID": "צילום תעודת זהות או דרכון של הנוסעים",
    "BANK": "פרטי חשבון בנק להעברת הפיצוי",
    "AIRLINE_REPLY": "מכתב או הודעה שקיבלתם מחברת התעופה",
    "DEPARTURE_TIME": "השעה שבה הטיסה המריאה בפועל",
    "NOTICE": "מתי חברת התעופה הודיעה לכם על הביטול",
}


def send_statement_of_claim(
    sender: EmailSender,
    claim: Claim,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    note: str | None = None,
) -> bool:
    """Send the pleading to the customer, with the document attached.

    The attachment is passed in rather than read from storage: the caller
    has just received the bytes from the operator's browser and there is
    no reason to write them, read them back, and hope the two agree.
    """
    reference = claim.reference
    flight = claim.check.flight_number if claim.check else ""

    body_lines = [
        f"שלום {claim.contact_name},",
        "",
        "מצורף כתב התביעה שהוכן בתיק שלכם" + (f" (טיסה {flight})" if flight else "") + ".",
        "",
        # Said plainly, because the next thing a person does with a legal
        # document is wonder whether they have to do something with it.
        "אין צורך לעשות דבר עם המסמך — הוא נשלח אליכם לידיעה ולתיעוד. "
        "אנחנו ממשיכים לטפל מול חברת התעופה ונעדכן בכל התקדמות.",
    ]
    if note:
        body_lines += ["", note]
    body_lines += [
        "",
        f"מספר התיק שלכם: {reference}",
        "",
        "בברכה,",
        "Skyclaim",
    ]
    text = "\n".join(body_lines)

    message = EmailMessage(
        to=claim.contact_email,
        subject=f"כתב התביעה בתיק {reference}",
        text=text,
        html=_as_html(body_lines),
        attachments=(
            EmailAttachment(
                filename=filename, content=content, content_type=content_type
            ),
        ),
    )
    sent = sender.send(message)
    logger.info(
        "statement of claim for %s to %s: %s",
        reference,
        claim.contact_email,
        "sent" if sent else "FAILED",
    )
    return sent


def send_request_for_items(
    sender: EmailSender,
    claim: Claim,
    *,
    items: list[str],
    note: str | None = None,
) -> bool:
    """Ask the customer for what is still missing.

    Takes keys from `REQUESTABLE`, not sentences. An unknown key is
    skipped rather than printed raw: a customer receiving "BOARDING_PASS"
    in the middle of a Hebrew letter learns nothing and trusts us less.
    """
    wanted = [REQUESTABLE[key] for key in items if key in REQUESTABLE]

    body_lines = [
        f"שלום {claim.contact_name},",
        "",
        "כדי להמשיך בטיפול בתיק שלכם חסרים לנו עוד כמה דברים:",
        "",
    ]
    body_lines += [f"  • {item}" for item in wanted]
    if note:
        body_lines += ["", note]
    body_lines += [
        "",
        "אפשר פשוט להשיב למייל הזה ולצרף את מה שיש. "
        "אם משהו לא זמין — כתבו לנו וננסה דרך אחרת.",
        "",
        f"מספר התיק שלכם: {claim.reference}",
        "",
        "בברכה,",
        "Skyclaim",
    ]
    text = "\n".join(body_lines)

    message = EmailMessage(
        to=claim.contact_email,
        subject=f"חסרים לנו כמה פרטים בתיק {claim.reference}",
        text=text,
        html=_as_html(body_lines),
    )
    sent = sender.send(message)
    logger.info(
        "request for items on %s to %s (%d item(s)): %s",
        claim.reference,
        claim.contact_email,
        len(wanted),
        "sent" if sent else "FAILED",
    )
    return sent


def _as_html(lines: list[str]) -> str:
    """The same words, marked up.

    Both parts are required by `EmailMessage` and that is deliberate --
    the plain-text part is what spam filters score and what renders when a
    client blocks HTML. Generating one from the other keeps them saying
    the same thing, which is the failure mode when they are written twice.
    """
    from html import escape

    body = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            body.append("<p style='margin:0 0 1em'></p>")
        elif stripped.startswith("•"):
            body.append(
                f"<p style='margin:0 0 .35em'>{escape(stripped)}</p>"
            )
        else:
            body.append(f"<p style='margin:0 0 1em'>{escape(stripped)}</p>")

    return (
        "<div dir='rtl' style=\"font-family:system-ui,'Segoe UI',sans-serif;"
        "font-size:15px;line-height:1.7;color:#1f2933\">"
        + "".join(body)
        + "</div>"
    )
