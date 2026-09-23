"""Deciding what to send, and to whom.

The adapters know how to send mail; this knows *whether* to. Keeping that
apart matters because the decision is the part with rules in it — we only
email an address somebody typed deliberately, we never send the same
confirmation twice — and the sending is the part that talks to a network.

Every function here returns quietly on anything that would stop it. A missing
address is not an error, it is a customer who did not ask to be emailed.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from app.db.models import Claim, EligibilityCheck
from app.storage.files import FileStorage
from app.email.base import EmailAttachment, EmailSender
from app.email.messages import (
    check_result,
    claim_submitted,
    ops_check_recorded,
    ops_claim_submitted,
)
from app.db.types import utc_now

logger = logging.getLogger("flight_system.email")


def send_claim_confirmation(
    sender: EmailSender,
    claim: Claim,
    *,
    base_url: str,
) -> bool:
    """Confirm a submitted claim.

    Idempotent: the send is recorded on the claim, so a retried request, a
    double-clicked Submit or a replayed background task cannot send it twice.
    A customer who gets the same confirmation three times stops trusting the
    next email we send, which is the one telling them the airline paid.
    """
    if claim.confirmation_sent_at is not None:
        logger.info("confirmation for %s already sent; skipping", claim.reference)
        return False

    check = claim.check
    snapshot = check.flight_snapshot or {}
    route = (
        f"{snapshot.get('origin_iata', '???')} → "
        f"{snapshot.get('destination_iata', '???')}"
    )
    amount = (
        f"{_symbol(check.best_currency)}{check.best_amount:,.2f}"
        if check.best_amount is not None
        else None
    )

    message = claim_submitted(
        to=claim.contact_email,
        contact_name=claim.contact_name.split()[0] or claim.contact_name,
        reference=claim.reference,
        flight_number=check.flight_number,
        route=route,
        amount=amount,
        passenger_count=len(claim.passengers),
        claim_url=f"{base_url.rstrip('/')}/claim/{check.id}",
    )

    if not sender.send(message):
        # Deliberately NOT recorded as sent. Leaving it unset means a retry can
        # pick it up later; recording a failed send would lose the email for
        # good and nobody would ever notice.
        return False

    claim.confirmation_sent_at = utc_now()
    return True


def send_check_result(
    sender: EmailSender,
    check: EligibilityCheck,
    *,
    base_url: str,
) -> bool:
    """Email the outcome of a check.

    Only when an address was given. The check form does not require one, so an
    address here means somebody typed it on purpose — and a result email nobody
    asked for is spam however useful we happen to think it is.
    """
    if not check.contact_email:
        return False
    if check.verdict is None:
        # NOT_FOUND and AMBIGUOUS are questions, not answers. Emailing "we
        # could not find your flight" to somebody who is still sitting in front
        # of the form is noise.
        return False

    snapshot = check.flight_snapshot or {}
    route = (
        f"{snapshot.get('origin_iata', '???')} → "
        f"{snapshot.get('destination_iata', '???')}"
    )
    amount = (
        f"{_symbol(check.best_currency)}{check.best_amount:,.2f}"
        if check.best_amount is not None
        else None
    )

    return sender.send(
        check_result(
            to=check.contact_email,
            flight_number=check.flight_number,
            route=route,
            verdict=check.verdict,
            amount=amount,
            check_url=f"{base_url.rstrip('/')}/check/{check.id}",
        )
    )


_SYMBOLS = {"EUR": "€", "GBP": "£", "ILS": "₪"}


def _symbol(currency: str | None) -> str:
    return _SYMBOLS.get(currency or "", f"{currency} " if currency else "")


# --- The files that travel with a claim --------------------------------------

# Resend accepts about 40MB per message and every mail server has some limit.
# Each upload is capped at 10MB, so a claim with five receipts can exceed what
# will actually send -- and an email refused for size is an email that silently
# does not arrive.
#
# Budgeted against the BASE64 size, which is what goes over the wire: encoding
# inflates bytes by roughly a third, so 15MB of files is about 20MB of message.
MAX_ATTACHED_BYTES = 15 * 1024 * 1024

# The one kind that does NOT travel.
#
# Identity numbers are kept out of the inbox deliberately -- encrypted at rest
# for a reason, and an inbox is the opposite of that: unencrypted, forwarded,
# backed up by a mail provider, searchable forever. A photograph of a passport
# is strictly worse than the number on it, so the same rule has to cover it.
#
# Nothing in the claim form uploads this kind today. The rule is here so that
# the day somebody adds an "upload your passport" step, the safe behaviour is
# already the default rather than something to remember.
_NEVER_ATTACHED = frozenset({"IDENTIFICATION"})


def attachments_for(
    claim: Claim, storage: FileStorage
) -> tuple[list[EmailAttachment], list[str]]:
    """The claim's documents as attachments, and the names of any left behind.

    Returns both because the message has to SAY what it is missing. A document
    list that silently drops the biggest receipt is worse than one that never
    promised to carry it: whoever is chasing the airline believes they have
    everything.

    A file that cannot be read is skipped rather than fatal. Storage on a
    managed host does not survive a deploy, so a claim submitted before one
    and emailed after it has rows pointing at bytes that are gone -- and the
    claim details are still worth sending without them.
    """
    attached: list[EmailAttachment] = []
    missing: list[str] = []
    budget = MAX_ATTACHED_BYTES

    for document in claim.documents:
        if document.kind in _NEVER_ATTACHED:
            missing.append(f"{document.original_filename} (נשמר במערכת)")
            continue
        try:
            content = storage.open(document.stored_path)
        except Exception:  # noqa: BLE001
            logger.warning(
                "document %s for claim %s could not be read from storage",
                document.id,
                claim.reference,
            )
            missing.append(document.original_filename)
            continue

        # The encoded size is what has to fit.
        cost = -(-len(content) * 4 // 3)
        if cost > budget:
            missing.append(document.original_filename)
            continue

        budget -= cost
        attached.append(
            EmailAttachment(
                filename=document.original_filename,
                content=content,
                content_type=document.content_type,
            )
        )

    return attached, missing


# --- What the company hears --------------------------------------------------


# The verdicts whose journey ENDS at the result screen. These get the company's
# copy immediately, because nothing else is coming.
#
# The other two -- ELIGIBLE and LIKELY_ELIGIBLE -- are silent here. Their
# customer is on their way to the claim form, and that form produces a message
# containing everything this one would have said and much more. Sending both
# means two inbox rows for one person, and an inbox where a row is not a person
# is an inbox nobody can work from.
_ENDS_HERE = frozenset({"NOT_ELIGIBLE", "NEEDS_REVIEW"})

# Six hex characters of the check's UUID. Long enough that a collision needs
# sixteen million checks, short enough to read down a phone screen and to
# survive the subject-line truncation every mail client does.
_REFERENCE_LENGTH = 6


def ops_reference(check_id: UUID) -> str:
    """The short handle for a check, as it appears in the subject line.

    Derived rather than stored: the UUID is already the identity, and a second
    identifier would be a second thing to keep in step. Taken from the front of
    the UUID because that is what somebody reading a URL will recognise.
    """
    return str(check_id).replace("-", "")[:_REFERENCE_LENGTH].upper()


def ops_wants_this_check(verdict: str | None) -> bool:
    """Whether a finished check is worth the company's inbox on its own.

    ONE EMAIL PER CUSTOMER is the rule, and the last step of their journey is
    where it belongs -- so an eligible customer is heard from once, when they
    submit, not twice.

    NEEDS_REVIEW is in the set for a different reason than NOT_ELIGIBLE. It is
    not the customer's answer, it is OUR failure: an airline missing from
    airlines.csv, an airport we do not recognise, a status nobody has seen.
    Waiting for a submission that may never come would make us blind to our own
    data gaps -- and that email is exactly how forty-three missing carriers were
    found. It is the cheapest monitoring in this system.

    A verdict of None means the check never decided at all, which is the same
    kind of failure and is treated the same way.
    """
    return verdict is None or verdict in _ENDS_HERE


def notify_ops_check(
    sender: EmailSender,
    check: EligibilityCheck,
    *,
    to: str,
    base_url: str,
) -> bool:
    """Copy a completed check to the company inbox, if it is one we want.

    Deliberately fire-and-forget and deliberately unrecorded: unlike the
    customer's confirmation, a duplicate here costs nothing worse than a
    duplicate line in a mailbox, and adding a column to track it would be
    bookkeeping for a problem nobody has.

    The filter lives here rather than at the call site so that every caller --
    the route today, a replay or a backfill tomorrow -- gets the same answer to
    "should this have been sent?".
    """
    if not to.strip():
        return False

    if not ops_wants_this_check(check.verdict):
        # Not silence for its own sake: this customer is mid-journey, and the
        # claim they are about to submit carries everything this would have.
        logger.info(
            "check %s is %s; the company hears about it when they submit",
            check.id,
            check.verdict,
        )
        return False

    snapshot = check.flight_snapshot or {}
    origin, destination = snapshot.get("origin_iata"), snapshot.get("destination_iata")
    route = f"{origin} → {destination}" if origin and destination else None

    message = ops_check_recorded(
        to=to.strip(),
        flight_number=check.flight_number,
        flight_date=check.flight_date.isoformat(),
        route=route,
        verdict=check.verdict,
        status=check.status,
        amount=_money(check),
        regulation=check.best_regulation,
        reason=check.message,
        contact_name=check.contact_name,
        reference=ops_reference(check.id),
        check_url=f"{base_url.rstrip('/')}/check/{check.id}",
    )
    return sender.send(message)


def notify_ops_claim(
    sender: EmailSender,
    claim: Claim,
    *,
    to: str,
    base_url: str,
    storage: FileStorage | None = None,
) -> bool:
    """Copy a submitted claim to the company inbox.

    This is the message that is actually work. It carries everything needed to
    act -- who, which flight, how much, what they spent, what the airline told
    them -- so that chasing an airline never requires opening the system.

    Identity numbers are NOT included. They are encrypted at rest for a reason,
    and an inbox is the opposite of that: unencrypted, forwarded, backed up by
    a mail provider, searchable forever. The passenger count makes it obvious
    they were collected; the numbers stay where they are protected.
    """
    if not to.strip():
        return False

    check = claim.check
    snapshot = check.flight_snapshot or {}
    origin, destination = snapshot.get("origin_iata"), snapshot.get("destination_iata")
    route = f"{origin} → {destination}" if origin and destination else None

    # Optional so that a caller with no storage configured still sends the
    # claim -- the details are the valuable part and must not depend on the
    # files being reachable.
    attached, missing = (
        attachments_for(claim, storage) if storage is not None else ([], [])
    )

    message = ops_claim_submitted(
        to=to.strip(),
        reference=claim.reference,
        contact_name=claim.contact_name,
        contact_email=claim.contact_email,
        contact_phone=claim.contact_phone,
        flight_number=check.flight_number,
        flight_date=check.flight_date.isoformat(),
        route=route,
        verdict=check.verdict,
        amount=_money(check),
        regulation=check.best_regulation,
        passengers=[(p.full_name, p.is_minor) for p in claim.passengers],
        expenses=[
            (e.category.replace("_", " ").title(),
             f"{_symbol(e.currency)}{e.amount:,.2f}")
            for e in claim.expenses
        ],
        documents=[d.original_filename for d in claim.documents],
        missing_documents=missing,
        booking_reference=claim.booking_reference,
        airline_reason=claim.airline_reason,
        cancellation_notice=claim.cancellation_notice,
        claim_url=f"{base_url.rstrip('/')}/claim/{check.id}",
    )
    # Attached here rather than passed into the builder: `ops_claim_submitted`
    # composes words, and what travels alongside them is not its business.
    if attached:
        message = replace(message, attachments=tuple(attached))
        logger.info(
            "claim %s: attaching %d document(s), %.1f MB",
            claim.reference,
            len(attached),
            sum(a.size_bytes for a in attached) / 1_048_576,
        )
    return sender.send(message)


def _money(check: EligibilityCheck) -> str | None:
    if check.best_amount is None:
        return None
    return f"{_symbol(check.best_currency)}{check.best_amount:,.2f}"
