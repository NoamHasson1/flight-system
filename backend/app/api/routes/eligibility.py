"""The eligibility endpoint.

The route is deliberately thin: validate, call the service, persist, serialise.
Every decision worth arguing about happened in `domain/rules`, and every failure
mode was already turned into an answer by `services/eligibility`. If this file
ever starts growing conditionals, something has leaked upwards.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_flight_provider, get_session
from app.db.repositories import get_check, record_check
from app.providers.base import FlightDataProvider
from app.schemas.eligibility import (
    EligibilityRequest,
    EligibilityResponse,
    FlightOptionOut,
    MoneyOut,
    OutcomeOut,
    flight_out,
)
from app.services.eligibility import CheckResult, check

router = APIRouter(prefix="/api/v1/eligibility", tags=["eligibility"])


@router.post(
    "/check",
    response_model=EligibilityResponse,
    summary="Check whether a flight is owed compensation",
    response_description="The verdict, with every regulation's reasoning.",
)
async def check_eligibility(
    payload: EligibilityRequest,
    provider: Annotated[FlightDataProvider, Depends(get_flight_provider)],
    session: Annotated[Session, Depends(get_session)],
) -> EligibilityResponse:
    """Look up a flight and decide whether the passenger is owed anything.

    Always returns 200 for a well-formed request, with the outcome in `status`.
    That is a deliberate choice: "no such flight" is not an HTTP error -- the
    endpoint worked, the lookup happened, and a record of it was stored. A 404
    here would tell a client the endpoint does not exist, and many HTTP
    libraries would discard the body that explains what actually went wrong.

    A malformed request is a different matter and returns 422.
    """
    outcome = await check(
        provider,
        payload.flight_number,
        payload.flight_date,
        option_key=payload.option_key,
    )

    # Every check is recorded, whatever it concluded. The failures are the most
    # valuable rows in the table: they are the review queue, and they are how
    # anyone notices a provider has started quietly failing.
    row = record_check(
        session,
        outcome,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
    )

    return _to_response(outcome, row.id)


@router.get(
    "/checks/{check_id}",
    response_model=EligibilityResponse,
    summary="Retrieve a previous check",
)
def read_check(
    check_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> EligibilityResponse:
    """Read back a stored check.

    Rebuilt from the stored snapshot rather than by asking the provider again:
    the answer must be the one the customer was actually given, not a fresh
    lookup that might now say something different.
    """
    row = get_check(session, check_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check with that id.",
        )

    detail = row.result_detail or {}
    snapshot = row.flight_snapshot or {}

    return EligibilityResponse(
        check_id=row.id,
        status=row.status,
        verdict=row.verdict,
        message=row.message,
        best_award=(
            MoneyOut(
                amount=str(row.best_amount),
                currency=row.best_currency or "",
                formatted=_format(row.best_amount, row.best_currency),
            )
            if row.best_amount is not None
            else None
        ),
        best_regulation=row.best_regulation,
        flight=_flight_from_snapshot(snapshot),
        outcomes=[
            OutcomeOut(
                regulation=item["regulation"],
                verdict=item["verdict"],
                applies=item["applies"],
                reason=item["reason"],
                award=(
                    MoneyOut(
                        amount=item["award"]["amount"],
                        currency=item["award"]["currency"],
                        formatted=_format_parts(
                            item["award"]["amount"], item["award"]["currency"]
                        ),
                    )
                    if item.get("award")
                    else None
                ),
            )
            for item in detail.get("outcomes", [])
        ],
        caveat=detail.get("caveat"),
        provider=row.provider,
    )


# --- serialisation -----------------------------------------------------------


def _to_response(outcome: CheckResult, check_id: UUID) -> EligibilityResponse:
    result = outcome.result
    return EligibilityResponse(
        check_id=check_id,
        status=outcome.status.value,
        verdict=outcome.verdict.value if outcome.verdict else None,
        message=outcome.message,
        best_award=MoneyOut.of(result.best_award) if result else None,
        best_regulation=result.best_regulation if result else None,
        flight=flight_out(outcome.flight) if outcome.flight else None,
        outcomes=[
            OutcomeOut(
                regulation=item.regulation,
                verdict=item.verdict.value,
                applies=item.applies,
                reason=item.reason,
                award=MoneyOut.of(item.award),
            )
            for item in (result.outcomes if result else ())
        ],
        options=[
            FlightOptionOut(
                key=option.key,
                route=option.route,
                label=option.label,
                scheduled_departure=option.scheduled_departure,
            )
            for option in outcome.options
        ],
        caveat=result.caveat if result else None,
        provider=outcome.provider,
    )


_SYMBOLS = {"EUR": "€", "GBP": "£", "ILS": "₪"}


def _format(amount: object, currency: str | None) -> str:
    return _format_parts(str(amount), currency or "")


def _format_parts(amount: str, currency: str) -> str:
    from decimal import Decimal

    return f"{_SYMBOLS.get(currency, currency + ' ')}{Decimal(amount):,.2f}"


def _flight_from_snapshot(snapshot: dict[str, object]):  # type: ignore[no-untyped-def]
    """Rebuild the flight block from what was stored.

    Returns None rather than a half-filled object when there is no snapshot --
    a NOT_FOUND or a failed lookup has no flight, and inventing an empty one
    would render in the UI as a real flight with blank fields.
    """
    if not snapshot:
        return None

    from app.schemas.eligibility import FlightOut

    return FlightOut(
        flight_number=str(snapshot["flight_number"]),
        flight_date=str(snapshot["flight_date"]),  # type: ignore[arg-type]
        airline=str(snapshot["airline_iata"]),
        route=f"{snapshot['origin_iata']} → {snapshot['destination_iata']}",
        origin=str(snapshot["origin_iata"]),
        origin_country=str(snapshot["origin_country"]),
        destination=str(snapshot["destination_iata"]),
        destination_country=str(snapshot["destination_country"]),
        distance_km=float(snapshot["distance_km"]),  # type: ignore[arg-type]
        status=str(snapshot["status"]),
        scheduled_departure=str(snapshot["scheduled_departure"]),  # type: ignore[arg-type]
        scheduled_arrival=str(snapshot["scheduled_arrival"]),  # type: ignore[arg-type]
        actual_departure=snapshot.get("actual_departure"),  # type: ignore[arg-type]
        actual_arrival=snapshot.get("actual_arrival"),  # type: ignore[arg-type]
        departure_delay_hours=snapshot.get("departure_delay_hours"),  # type: ignore[arg-type]
        arrival_delay_hours=snapshot.get("arrival_delay_hours"),  # type: ignore[arg-type]
    )
