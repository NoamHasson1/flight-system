"""The only place that reads or writes eligibility_checks.

Keeping persistence behind functions -- rather than letting endpoints build ORM
objects -- means the shape of a stored check is decided once. It also keeps the
domain clean: `FlightFacts` and `EligibilityResult` know nothing about
databases, so something has to translate, and this is it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EligibilityCheck
from app.db.types import jsonable
from app.domain.models import FlightFacts, Money
from app.domain.rules.engine import EligibilityResult
from app.services.eligibility import CheckResult, CheckStatus

# --- Writing -----------------------------------------------------------------


def record_check(
    session: Session,
    outcome: CheckResult,
    *,
    contact_name: str | None = None,
    contact_email: str | None = None,
) -> EligibilityCheck:
    """Store one check. Every check, whatever it concluded.

    A NOT_FOUND and a failed lookup are recorded exactly like a verdict. Storing
    only the eligible ones would throw away the review queue, the record of what
    the customer was actually told, and any way to notice that a provider has
    started failing.
    """
    row = EligibilityCheck(
        flight_number=outcome.flight_number,
        flight_date=outcome.flight_date,
        contact_name=_clean(contact_name),
        contact_email=_clean(contact_email, lower=True),
        status=outcome.status.value,
        verdict=outcome.verdict.value if outcome.verdict else None,
        message=outcome.message or _review_summary(outcome),
        provider=outcome.provider,
        flight_snapshot=flight_snapshot(outcome.flight),
        result_detail=result_detail(outcome.result),
        provider_payload=dict(outcome.raw.raw) if outcome.raw else None,
    )

    award = outcome.result.best_award if outcome.result else None
    if award is not None and outcome.result is not None:
        row.best_regulation = outcome.result.best_regulation
        row.best_amount = award.amount
        row.best_currency = award.currency.value

    session.add(row)
    session.flush()  # assigns the id without ending the caller's transaction
    return row


# --- Reading -----------------------------------------------------------------


def get_check(session: Session, check_id: uuid.UUID) -> EligibilityCheck | None:
    return session.get(EligibilityCheck, check_id)


def list_checks(
    session: Session,
    *,
    verdict: str | None = None,
    status: str | None = None,
    flight_number: str | None = None,
    flight_date: date | None = None,
    contact_email: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[EligibilityCheck]:
    """Newest first, filtered, paginated.

    Always paginated -- an unbounded listing is fine on day one and a problem
    on day four hundred, and by then it is in a dashboard nobody wants to touch.
    """
    query = select(EligibilityCheck).order_by(EligibilityCheck.created_at.desc())

    if verdict is not None:
        query = query.where(EligibilityCheck.verdict == verdict)
    if status is not None:
        query = query.where(EligibilityCheck.status == status)
    if flight_number is not None:
        query = query.where(
            EligibilityCheck.flight_number == flight_number.strip().upper()
        )
    if flight_date is not None:
        query = query.where(EligibilityCheck.flight_date == flight_date)
    if contact_email is not None:
        query = query.where(
            EligibilityCheck.contact_email == contact_email.strip().lower()
        )

    return session.scalars(query.limit(limit).offset(offset)).all()


def count_checks(session: Session, *, verdict: str | None = None) -> int:
    from sqlalchemy import func

    query = select(func.count()).select_from(EligibilityCheck)
    if verdict is not None:
        query = query.where(EligibilityCheck.verdict == verdict)
    return session.scalar(query) or 0


def find_others_on_the_same_flight(
    session: Session, row: EligibilityCheck
) -> Sequence[EligibilityCheck]:
    """Everyone else who checked this flight.

    Several passengers on one disrupted flight usually check separately. They
    belong in one claim: cheaper to run and far stronger against the airline
    than the same facts argued five times.
    """
    query = (
        select(EligibilityCheck)
        .where(
            EligibilityCheck.flight_number == row.flight_number,
            EligibilityCheck.flight_date == row.flight_date,
            EligibilityCheck.id != row.id,
        )
        .order_by(EligibilityCheck.created_at)
    )
    return session.scalars(query).all()


# --- Turning domain objects into stored JSON ---------------------------------


def flight_snapshot(flight: FlightFacts | None) -> dict[str, Any] | None:
    """Exactly the facts the verdict was computed from.

    The derived delays are stored alongside the raw timestamps even though they
    could be recomputed. Someone reading this row in a support conversation
    should not have to do arithmetic across timezones to see what happened.
    """
    if flight is None:
        return None
    return jsonable(
        {
            "flight_number": flight.flight_number,
            "flight_date": flight.flight_date,
            "airline_iata": flight.airline_iata,
            "airline_country": flight.airline_country,
            "origin_iata": flight.origin_iata,
            "origin_country": flight.origin_country,
            "destination_iata": flight.destination_iata,
            "destination_country": flight.destination_country,
            "distance_km": round(flight.distance_km, 1),
            "scheduled_departure": flight.scheduled_departure,
            "actual_departure": flight.actual_departure,
            "scheduled_arrival": flight.scheduled_arrival,
            "actual_arrival": flight.actual_arrival,
            "status": flight.status,
            "departure_delay_hours": flight.departure_delay_hours,
            "arrival_delay_hours": flight.arrival_delay_hours,
        }
    )


def result_detail(result: EligibilityResult | None) -> dict[str, Any] | None:
    """Every law's answer, with its reasoning.

    Stored in full rather than just the winner, so that a question six months
    from now -- "why did it say no?" -- has an answer that does not depend on
    the rules still being what they were.
    """
    if result is None:
        return None
    return jsonable(
        {
            "verdict": result.verdict,
            "best_regulation": result.best_regulation,
            "best_award": _money(result.best_award),
            "caveat": result.caveat,
            "outcomes": [
                {
                    "regulation": outcome.regulation,
                    "verdict": outcome.verdict,
                    "applies": outcome.applies,
                    "reason": outcome.reason,
                    "award": _money(outcome.award),
                }
                for outcome in result.outcomes
            ],
        }
    )


def _review_summary(outcome: CheckResult) -> str | None:
    """What an operator should read first about a row that needs attention.

    A cancelled flight is DECIDED -- the rules ran and reached NEEDS_REVIEW --
    so it carries no service-level message, and the review queue would show a
    blank line. The open question is in `result_detail`, but a queue nobody can
    skim is a queue nobody works.
    """
    if outcome.result is None:
        return None
    reviews = outcome.result.review_outcomes
    return reviews[0].reason if reviews else None


def _money(award: Money | None) -> dict[str, Any] | None:
    if award is None:
        return None
    return {"amount": str(award.amount), "currency": award.currency.value}


def _clean(value: str | None, *, lower: bool = False) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text.lower() if lower else text


__all__ = [
    "CheckStatus",
    "count_checks",
    "find_others_on_the_same_flight",
    "flight_snapshot",
    "get_check",
    "list_checks",
    "record_check",
    "result_detail",
]
