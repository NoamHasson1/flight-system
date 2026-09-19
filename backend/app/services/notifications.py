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

from app.db.models import Claim, EligibilityCheck
from app.email.base import EmailSender
from app.email.messages import check_result, claim_submitted
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
