"""The admin API.

Read-only, and guarded by a shared secret on every route. It serves the three
questions an operator actually has: what needs a human, who is claiming what,
and how many people are we turning away.

It WAS read-only, and mostly still is. Three endpoints now write, and the
reasoning that kept the others read-only is what shapes them:

  * hide / restore -- reversible by construction. The screen says "delete"
    because that is what an operator means; what it does is stamp
    `hidden_at`. Nothing is destroyed, so a leaked key cannot be used to
    lose a claim, and a misclick is one button away from undone.

  * claim status -- an operator moving a claim along its own lifecycle,
    which is the work this dashboard exists to support. It validates
    against the enum, so a dashboard cannot invent a stage no report counts.

Still nothing here deletes a row, edits a customer's details, or touches
money. Those belong in a workflow with an audit trail, not in a list.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from urllib.parse import quote

from fastapi import Response

from app.api.deps import get_file_storage, get_session, require_admin
from app.db import claims as claims_repo
from app.db import crm as crm_repo
from app.db import repositories as checks_repo
from app.db.models import Claim, Document, EligibilityCheck
from app.schemas.admin import (
    CheckDetail,
    CheckRow,
    ClaimRow,
    CustomerCounts,
    CustomerDetail,
    CustomerRow,
    ClaimStatusUpdate,
    DocumentRow,
    HideRequest,
    Moved,
    ExpenseRow,
    Page,
    PassengerRow,
    Summary,
)
from app.storage.files import FileStorage

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


# --- the CRM -----------------------------------------------------------------
#
# `/checks` and `/claims` answer "what did the system do". These answer "who
# is this person and what do I owe them", which is a different question with
# a different shape: one row per customer, both tables joined, and the
# evidence left behind until somebody asks for it.


@router.get(
    "/customers",
    response_model=Page[CustomerRow],
    summary="Everyone who has asked us about a flight",
)
def list_customers(
    session: Annotated[Session, Depends(get_session)],
    verdict: Annotated[
        str | None, Query(description="ELIGIBLE | LIKELY_ELIGIBLE | NOT_ELIGIBLE | NEEDS_REVIEW")
    ] = None,
    search: Annotated[
        str | None, Query(description="Name, email, flight number or claim reference")
    ] = None,
    has_claim: Annotated[
        bool | None, Query(description="Only those who filed, or only those who did not")
    ] = None,
    include_anonymous: Annotated[
        bool,
        Query(
            description=(
                "Include checks with no name and no email -- people who typed "
                "a flight number and left. Off by default: there is nobody to "
                "contact, and thousands of them would bury the rest."
            )
        ),
    ] = False,
    hidden: Annotated[
        bool,
        Query(description="Show ONLY the customers that have been hidden."),
    ] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CustomerRow]:
    records = crm_repo.list_customers(
        session,
        verdict=verdict,
        search=search,
        has_claim=has_claim,
        include_anonymous=include_anonymous,
        hidden=hidden,
        limit=limit,
        offset=offset,
    )
    return Page[CustomerRow](
        items=[_customer_row(r) for r in records],
        total=crm_repo.count_customers(
            session,
            verdict=verdict,
            search=search,
            has_claim=has_claim,
            include_anonymous=include_anonymous,
            hidden=hidden,
        ),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/customers/stats",
    response_model=CustomerCounts,
    summary="The four numbers above the list",
)
def customer_stats(
    session: Annotated[Session, Depends(get_session)],
    include_anonymous: bool = False,
) -> CustomerCounts:
    """Declared BEFORE `/customers/{check_id}`.

    FastAPI matches routes in declaration order. The other way round, a
    request for /customers/stats is handed to the detail route, which tries
    to parse "stats" as a UUID and answers 422 -- a confusing failure for
    something that looks like it should obviously work.
    """
    return CustomerCounts(
        **crm_repo.customer_counts(session, include_anonymous=include_anonymous)
    )


@router.get(
    "/customers/{check_id}",
    response_model=CustomerDetail,
    summary="Everything one customer submitted",
)
def read_customer(
    check_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> CustomerDetail:
    """Keyed on the CHECK, not the claim.

    Every customer has a check; only some have a claim. Keying on the claim
    would mean the detail button works for the people who got through and
    404s for everybody who was refused -- who are the majority, and the ones
    worth revisiting when a rule changes.
    """
    check = checks_repo.get_check(session, check_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such customer."
        )
    claim = claims_repo.find_claim_for_check(session, check_id)
    record = crm_repo.CustomerRecord(check=check, claim=claim)

    return CustomerDetail(
        **_customer_row(record).model_dump(),
        booking_reference=claim.booking_reference if claim else None,
        airline_reason=claim.airline_reason if claim else None,
        cancellation_notice=claim.cancellation_notice if claim else None,
        notes=claim.notes if claim else None,
        passengers=[
            PassengerRow(
                full_name=p.full_name,
                national_id=p.national_id,
                is_minor=p.is_minor,
            )
            for p in (claim.passengers if claim else [])
        ],
        expenses=[
            ExpenseRow(
                id=e.id,
                category=e.category,
                amount=str(e.amount),
                currency=e.currency,
                description=e.description,
            )
            for e in (claim.expenses if claim else [])
        ],
        documents=[_document_row(d) for d in (claim.documents if claim else [])],
        expense_totals=(
            {
                currency: str(total)
                for currency, total in sorted(claims_repo.expense_totals(claim).items())
            }
            if claim
            else {}
        ),
        result_detail=check.result_detail,
        flight_snapshot=check.flight_snapshot,
    )


@router.get(
    "/documents/{document_id}",
    summary="Download one uploaded file",
    response_class=Response,
)
def read_document(
    document_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> Response:
    """The bytes of a receipt or a boarding pass.

    THE KEY TRAVELS IN A HEADER, WHICH SHAPES HOW THIS IS USED. A browser
    cannot put a header on an `<a href>`, so the operator's screen fetches
    this with the key and hands the blob to the browser. That is deliberate:
    the alternative is a token in the URL, and URLs are written to server
    logs, proxy logs and browser history. A link to somebody's passport scan
    should not be sitting in three logs.

    `Content-Disposition: attachment` and a fixed content type, because the
    bytes are customer-uploaded and rendering them inline in the operator's
    own origin would make an uploaded SVG or HTML file a script running on
    the admin page. The upload path already restricts types; this is the
    second lock on the same door.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such document."
        )

    try:
        content = storage.open(document.stored_path)
    except (FileNotFoundError, OSError) as exc:
        # The row exists and the bytes do not. Worth saying plainly rather
        # than as a 500: it means storage was lost or moved, which is an
        # operations problem and not a bad request.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The file is recorded but its contents are missing.",
        ) from exc

    return Response(
        content=content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": _disposition(document.original_filename),
            # Never cached by a shared proxy: this is one customer's document.
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _customer_row(record: crm_repo.CustomerRecord) -> CustomerRow:
    check, claim = record.check, record.claim
    return CustomerRow(
        check_id=check.id,
        created_at=check.created_at,
        contact_name=record.contact_name,
        contact_email=record.contact_email,
        contact_phone=record.contact_phone,
        flight_number=check.flight_number,
        flight_date=check.flight_date,
        verdict=check.verdict,
        status=check.status,
        best_amount=str(check.best_amount) if check.best_amount is not None else None,
        best_currency=check.best_currency,
        claim_id=claim.id if claim else None,
        claim_reference=claim.reference if claim else None,
        claim_status=claim.status if claim else None,
        claim_submitted_at=claim.submitted_at if claim else None,
        hidden_at=check.hidden_at,
        passenger_count=len(claim.passengers) if claim else 0,
        document_count=len(claim.documents) if claim else 0,
    )


def _document_row(document: Document) -> DocumentRow:
    return DocumentRow(
        id=document.id,
        kind=document.kind,
        original_filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
        expense_id=document.expense_id,
    )


def _disposition(name: str) -> str:
    """A Content-Disposition that keeps a Hebrew filename readable.

    Most filenames here are Hebrew, and HTTP header values are Latin-1. The
    first version of this replaced every non-ASCII character with an
    underscore, which was safe and useless: a receipt downloaded as
    "____.jpg" is a file the operator then has to open to identify.

    RFC 5987 exists for this. Two parameters are emitted:

        filename="____.jpg"                     the ASCII fallback
        filename*=UTF-8\'\'%D7%A7%D7%91...      the real name

    Every browser in use prefers `filename*` and ignores the other; anything
    that does not understand it still gets a valid, if ugly, name. The
    fallback keeps the extension, because that is the part an operating
    system needs.

    The ASCII form is also where injection would happen -- a quote or a
    newline in a customer-supplied name could close the header value and
    start another -- so it keeps the strict filter. `quote` handles the
    encoded form, which cannot contain a raw quote by construction.
    """
    fallback = "".join(
        c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in name
    ).strip() or "document"
    encoded = quote(name, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8\'\'{encoded}"


@router.post(
    "/customers/hide",
    response_model=Moved,
    summary="Remove customers from the list (reversibly)",
)
def hide_customers(
    payload: HideRequest,
    session: Annotated[Session, Depends(get_session)],
) -> Moved:
    """What the screen's delete button does.

    Nothing is destroyed. The row keeps its claim, its passengers and its
    uploaded passports, and `/customers?hidden=true` shows everything that
    has been put away.

    This is deliberately not a DELETE verb. DELETE would describe something
    this does not do, and the next person reading the route list would
    reasonably assume the data is gone.
    """
    moved = crm_repo.set_hidden(session, payload.check_ids, hidden=True)
    session.commit()
    return Moved(moved=moved)


@router.post(
    "/customers/restore",
    response_model=Moved,
    summary="Put hidden customers back in the list",
)
def restore_customers(
    payload: HideRequest,
    session: Annotated[Session, Depends(get_session)],
) -> Moved:
    """The undo.

    Its existence is the whole argument for hiding rather than deleting:
    the operator's very next action after an accidental bulk delete has
    somewhere to go.
    """
    moved = crm_repo.set_hidden(session, payload.check_ids, hidden=False)
    session.commit()
    return Moved(moved=moved)


@router.patch(
    "/claims/{claim_id}/status",
    response_model=ClaimRow,
    summary="Move a claim along its lifecycle",
)
def update_claim_status(
    claim_id: UUID,
    payload: ClaimStatusUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ClaimRow:
    """Advance a claim: submitted, sent to the airline, settled, rejected.

    The eight stages already existed in the model and nothing could move a
    claim between them except code. That made the status column decorative
    -- it only ever read DRAFT or SUBMITTED, whatever had really happened.

    No transition rules. A real claim goes backwards: an airline asks for
    another document, something is withdrawn and refiled. Encoding a
    one-way pipeline would mean an operator staring at a correct value they
    are not allowed to set, which is how people start keeping the real
    status in a spreadsheet.
    """
    claim = claims_repo.get_claim(session, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such claim."
        )
    try:
        claims_repo.set_status(session, claim, payload.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Not a claim status: {payload.status}",
        ) from exc
    session.commit()
    return _claim_row(claim)
