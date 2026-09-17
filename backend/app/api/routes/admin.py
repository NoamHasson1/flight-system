"""The admin API.

Read-only, and guarded by a shared secret on every route. It serves the three
questions an operator actually has: what needs a human, who is claiming what,
and how many people are we turning away.

No endpoint here changes anything. Deliberate: a read-only surface cannot be
used to corrupt data even if the key leaks, and every state change worth making
belongs in a workflow with its own audit trail rather than in a dashboard.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_admin
from app.db import claims as claims_repo
from app.db import repositories as checks_repo
from app.db.models import Claim, EligibilityCheck
from app.schemas.admin import CheckDetail, CheckRow, ClaimRow, Page, Summary

# The guard is applied to the router, not to each route. One line, and it
# cannot be forgotten on the next endpoint somebody adds.
router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

# A ceiling, not a suggestion. Without one, ?limit=1000000 is a denial of
# service anybody can perform with a browser.
MAX_LIMIT = 200


@router.get("/summary", response_model=Summary, summary="Counts for the dashboard")
def summary(session: Annotated[Session, Depends(get_session)]) -> Summary:
    checks = checks_repo.check_summary(session)
    return Summary(
        checks_total=checks_repo.count_checks(session),
        checks_by_verdict=checks["checks_by_verdict"],
        checks_by_status=checks["checks_by_status"],
        claims_total=claims_repo.count_claims(session),
        claims_by_status=claims_repo.claim_summary(session),
        eligible_value_by_currency=checks["eligible_value_by_currency"],
        needs_review=checks_repo.count_checks(session, verdict="NEEDS_REVIEW"),
    )


@router.get(
    "/checks", response_model=Page[CheckRow], summary="Browse eligibility checks"
)
def list_checks(
    session: Annotated[Session, Depends(get_session)],
    verdict: Annotated[str | None, Query(description="ELIGIBLE | NOT_ELIGIBLE | NEEDS_REVIEW")] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    flight_number: str | None = None,
    flight_date: date | None = None,
    contact_email: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CheckRow]:
    """Newest first.

    `verdict=NEEDS_REVIEW` is the query this endpoint exists for: the queue of
    everything the system could not decide, which must be worked by a person
    rather than quietly becoming a no.
    """
    filters = {
        "verdict": verdict,
        "status": status_filter,
        "flight_number": flight_number,
        "flight_date": flight_date,
        "contact_email": contact_email,
    }
    rows = checks_repo.list_checks(session, limit=limit, offset=offset, **filters)  # type: ignore[arg-type]
    return Page[CheckRow](
        items=[_check_row(session, row) for row in rows],
        total=checks_repo.count_checks(session, **filters),  # type: ignore[arg-type]
        limit=limit,
        offset=offset,
    )


@router.get(
    "/checks/{check_id}", response_model=CheckDetail, summary="Open one check"
)
def read_check(
    check_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> CheckDetail:
    row = checks_repo.get_check(session, check_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No check with that id."
        )

    others = checks_repo.find_others_on_the_same_flight(session, row)
    return CheckDetail(
        **_check_row(session, row).model_dump(),
        flight_snapshot=row.flight_snapshot,
        result_detail=row.result_detail,
        provider_payload=row.provider_payload,
        others_on_this_flight=[_check_row(session, other) for other in others],
    )


@router.get("/claims", response_model=Page[ClaimRow], summary="Browse claims")
def list_claims(
    session: Annotated[Session, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    contact_email: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ClaimRow]:
    rows = claims_repo.list_claims(
        session, status=status_filter, contact_email=contact_email,
        limit=limit, offset=offset,
    )
    return Page[ClaimRow](
        items=[_claim_row(claim) for claim in rows],
        total=claims_repo.count_claims(session, status=status_filter),
        limit=limit,
        offset=offset,
    )


# --- serialisation -----------------------------------------------------------


def _check_row(session: Session, row: EligibilityCheck) -> CheckRow:
    return CheckRow(
        id=row.id,
        created_at=row.created_at,
        flight_number=row.flight_number,
        flight_date=row.flight_date,
        contact_name=row.contact_name,
        contact_email=row.contact_email,
        status=row.status,
        verdict=row.verdict,
        message=row.message,
        best_regulation=row.best_regulation,
        best_amount=str(row.best_amount) if row.best_amount is not None else None,
        best_currency=row.best_currency,
        provider=row.provider,
        has_claim=claims_repo.find_claim_for_check(session, row.id) is not None,
    )


def _claim_row(claim: Claim) -> ClaimRow:
    check = claim.check
    return ClaimRow(
        id=claim.id,
        reference=claim.reference,
        created_at=claim.created_at,
        submitted_at=claim.submitted_at,
        status=claim.status,
        contact_name=claim.contact_name,
        contact_email=claim.contact_email,
        flight_number=check.flight_number,
        flight_date=check.flight_date,
        verdict=check.verdict,
        best_amount=str(check.best_amount) if check.best_amount is not None else None,
        best_currency=check.best_currency,
        passenger_count=len(claim.passengers),
        expense_count=len(claim.expenses),
        document_count=len(claim.documents),
        expense_totals={
            currency: str(total)
            for currency, total in sorted(claims_repo.expense_totals(claim).items())
        },
    )
