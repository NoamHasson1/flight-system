"""Creating and reading claims.

The counterpart to `repositories.py`, which owns eligibility_checks. Split
because the two have almost nothing to do with each other: a check is written
once and never changed, while a claim is assembled over several steps by a
person who will get halfway and come back tomorrow.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Claim,
    ClaimStatus,
    Document,
    DocumentKind,
    EligibilityCheck,
    Expense,
    ExpenseCategory,
    Passenger,
)
from app.db.types import utc_now

# Deliberately missing I, O, 0 and 1. These references get read aloud on the
# phone and copied off screenshots, and those four characters are the ones
# people get wrong.
_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REFERENCE_LENGTH = 6
_REFERENCE_ATTEMPTS = 5


class ClaimError(Exception):
    """A claim could not be created or changed, for a reason the caller should
    explain to the customer rather than log."""


def generate_reference(when: date | None = None) -> str:
    """A short, human-quotable claim reference: FS-2026-K7M9QX.

    Random rather than sequential. A sequential reference tells every customer
    how many claims you have ever handled, and lets them read somebody else's by
    subtracting one.
    """
    year = (when or utc_now().date()).year
    body = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(_REFERENCE_LENGTH))
    return f"FS-{year}-{body}"


# --- Creating ----------------------------------------------------------------


def create_claim(
    session: Session,
    check: EligibilityCheck,
    *,
    contact_name: str,
    contact_email: str,
    contact_phone: str | None = None,
    booking_reference: str | None = None,
    airline_reason: str | None = None,
    cancellation_notice_days: int | None = None,
    notes: str | None = None,
) -> Claim:
    """Start a claim from a check.

    Deliberately does NOT copy the verdict, the flight or the amount out of the
    check. They live there already, and a copy is a second version of the truth
    that will eventually disagree with the first.
    """
    if not _clean(contact_name):
        raise ClaimError("a claim needs a contact name")
    if not _clean(contact_email):
        raise ClaimError("a claim needs a contact email address")

    existing = find_claim_for_check(session, check.id)
    if existing is not None:
        raise ClaimError(
            f"this check already has a claim ({existing.reference}). "
            "Add passengers to that one rather than starting another."
        )

    claim = Claim(
        reference=_unique_reference(session),
        check_id=check.id,
        status=ClaimStatus.DRAFT.value,
        contact_name=_clean(contact_name) or "",
        contact_email=(_clean(contact_email) or "").lower(),
        contact_phone=_clean(contact_phone),
        booking_reference=_upper(booking_reference),
        airline_reason=_clean(airline_reason),
        cancellation_notice_days=cancellation_notice_days,
        notes=_clean(notes),
    )
    session.add(claim)
    session.flush()
    return claim


def add_passenger(
    session: Session,
    claim: Claim,
    *,
    full_name: str,
    national_id: str | None = None,
    is_minor: bool = False,
) -> Passenger:
    """Add one passenger.

    Compensation is per passenger, so a family of four is four awards -- which
    is why this is a row and not a name field on the claim.
    """
    if not _clean(full_name):
        raise ClaimError("a passenger needs a full name")

    passenger = Passenger(
        claim_id=claim.id,
        full_name=_clean(full_name) or "",
        national_id=_clean(national_id),
        is_minor=is_minor,
    )
    session.add(passenger)
    session.flush()
    return passenger


def add_expense(
    session: Session,
    claim: Claim,
    *,
    category: ExpenseCategory | str,
    amount: Decimal | str | int,
    currency: str,
    description: str | None = None,
    incurred_on: date | None = None,
) -> Expense:
    """Record one out-of-pocket cost, in the currency it was actually paid in."""
    if isinstance(amount, float):
        # The same refusal `Money` makes, for the same reason: a float that
        # reaches us has already lost precision.
        raise ClaimError("expense amounts must not be floats; pass a string or Decimal")

    value = Decimal(amount)
    if value <= 0:
        raise ClaimError(f"an expense must be a positive amount, got {value}")
    if len(currency.strip()) != 3:
        raise ClaimError(f"currency must be a three-letter code, got {currency!r}")

    expense = Expense(
        claim_id=claim.id,
        category=ExpenseCategory(category).value,
        description=_clean(description),
        amount=value,
        currency=currency.strip().upper(),
        incurred_on=incurred_on,
    )
    session.add(expense)
    session.flush()
    return expense


def add_document(
    session: Session,
    claim: Claim,
    *,
    kind: DocumentKind | str,
    original_filename: str,
    stored_path: str,
    content_type: str,
    size_bytes: int,
    expense: Expense | None = None,
) -> Document:
    """Record an uploaded file.

    `stored_path` comes from the storage layer, never from the filename: a
    filename arriving from a browser is attacker-controlled input, and one
    containing `../` is the oldest trick there is.
    """
    if expense is not None and expense.claim_id != claim.id:
        raise ClaimError("that expense belongs to a different claim")
    if size_bytes <= 0:
        raise ClaimError("an uploaded document cannot be empty")

    document = Document(
        claim_id=claim.id,
        expense_id=expense.id if expense else None,
        kind=DocumentKind(kind).value,
        original_filename=original_filename.strip()[:255],
        stored_path=stored_path,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    session.add(document)
    session.flush()
    return document


# --- Changing ----------------------------------------------------------------


def submit_claim(session: Session, claim: Claim) -> Claim:
    """Hand the claim over.

    Refuses an empty claim. A submission with no passengers is not a claim, and
    letting one through means somebody has to chase it later -- by which time the
    customer has forgotten they ever started.
    """
    if claim.status != ClaimStatus.DRAFT.value:
        raise ClaimError(f"claim {claim.reference} has already been submitted")
    if not claim.passengers:
        raise ClaimError("add at least one passenger before submitting")

    claim.status = ClaimStatus.SUBMITTED.value
    claim.submitted_at = utc_now()
    session.flush()
    return claim


def set_status(session: Session, claim: Claim, status: ClaimStatus | str) -> Claim:
    claim.status = ClaimStatus(status).value
    session.flush()
    return claim


# --- Reading -----------------------------------------------------------------


def get_claim(session: Session, claim_id: uuid.UUID) -> Claim | None:
    return session.get(Claim, claim_id)


def find_claim_by_reference(session: Session, reference: str) -> Claim | None:
    """Look a claim up the way a customer would quote it.

    Case- and space-insensitive, because it will be typed from a screenshot.
    """
    normalised = reference.strip().upper().replace(" ", "")
    return session.scalar(select(Claim).where(Claim.reference == normalised))


def find_claim_for_check(session: Session, check_id: uuid.UUID) -> Claim | None:
    return session.scalar(select(Claim).where(Claim.check_id == check_id))


def list_claims(
    session: Session,
    *,
    status: str | None = None,
    contact_email: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Claim]:
    query = select(Claim).order_by(Claim.created_at.desc())
    if status is not None:
        query = query.where(Claim.status == status)
    if contact_email is not None:
        query = query.where(Claim.contact_email == contact_email.strip().lower())
    return session.scalars(query.limit(limit).offset(offset)).all()


def count_claims(session: Session, *, status: str | None = None) -> int:
    from sqlalchemy import func

    query = select(func.count()).select_from(Claim)
    if status is not None:
        query = query.where(Claim.status == status)
    return session.scalar(query) or 0


def claim_summary(session: Session) -> dict[str, int]:
    from sqlalchemy import func

    return {
        str(status): count
        for status, count in session.execute(
            select(Claim.status, func.count()).group_by(Claim.status)
        ).all()
    }


def expense_totals(claim: Claim) -> dict[str, Decimal]:
    """Total expenses per currency.

    Per currency, never summed across them. A hotel in euro and a taxi in
    shekels do not add up to a number, and inventing an exchange rate to make
    them would be quietly making up a figure someone will later have to defend.
    """
    totals: dict[str, Decimal] = {}
    for expense in claim.expenses:
        totals[expense.currency] = totals.get(expense.currency, Decimal("0")) + expense.amount
    return totals


# --- Helpers -----------------------------------------------------------------


def _unique_reference(session: Session) -> str:
    """Generate a reference, retrying on the astronomically unlikely collision.

    32^6 is about a billion, so a clash is rare -- but "rare" and "never" are
    different, and the difference surfaces as an IntegrityError in front of a
    customer at the worst possible moment.
    """
    for _ in range(_REFERENCE_ATTEMPTS):
        candidate = generate_reference()
        if session.scalar(select(Claim.id).where(Claim.reference == candidate)) is None:
            return candidate
    raise ClaimError("could not allocate a unique claim reference")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _upper(value: str | None) -> str | None:
    cleaned = _clean(value)
    return cleaned.upper() if cleaned else None


__all__ = [
    "ClaimError",
    "claim_summary",
    "count_claims",
    "add_document",
    "add_expense",
    "add_passenger",
    "create_claim",
    "expense_totals",
    "find_claim_by_reference",
    "find_claim_for_check",
    "generate_reference",
    "get_claim",
    "list_claims",
    "set_status",
    "submit_claim",
]
