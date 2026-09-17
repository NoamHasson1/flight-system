"""Claim submission and document upload."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_file_storage, get_session
from app.db import claims as repo
from app.db.models import Claim, DocumentKind
from app.db.repositories import get_check
from app.schemas.claims import (
    ClaimCreate,
    ClaimOut,
    DocumentOut,
    DocumentUploadResponse,
    ExpenseOut,
    PassengerOut,
)
from app.storage.files import FileStorage, UploadRejected

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])

_SYMBOLS = {"EUR": "€", "GBP": "£", "ILS": "₪"}

# A check that never identified a flight has nothing to claim about. Note what
# is NOT here: NOT_ELIGIBLE. We told that customer no, but our verdict rests on
# facts we could not see -- why the flight was late, what the airline said -- so
# refusing to let them proceed would make our estimate final, which it is not.
_UNCLAIMABLE = {"NOT_FOUND", "AMBIGUOUS"}


@router.post(
    "",
    response_model=ClaimOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a claim from an eligibility check",
)
def create_claim(
    payload: ClaimCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ClaimOut:
    """Create a claim, with its passengers and expenses in one call.

    One request rather than several, because a claim assembled over four round
    trips can fail on the third and leave a half-built record that nobody can
    finish and nobody will ever chase.
    """
    check = get_check(session, payload.check_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No eligibility check with that id. Please run the check again.",
        )

    if check.status in _UNCLAIMABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That check did not identify a flight, so there is nothing to "
                "claim for yet. Please run the check again."
            ),
        )

    try:
        claim = repo.create_claim(
            session,
            check,
            contact_name=payload.contact_name,
            contact_email=str(payload.contact_email),
            contact_phone=payload.contact_phone,
            booking_reference=payload.booking_reference,
            airline_reason=payload.airline_reason,
            cancellation_notice_days=payload.cancellation_notice_days,
            notes=payload.notes,
        )
        for passenger in payload.passengers:
            repo.add_passenger(
                session,
                claim,
                full_name=passenger.full_name,
                national_id=passenger.national_id,
                is_minor=passenger.is_minor,
            )
        for expense in payload.expenses:
            repo.add_expense(
                session,
                claim,
                category=expense.category,
                amount=Decimal(expense.amount),
                currency=expense.currency,
                description=expense.description,
                incurred_on=expense.incurred_on,
            )
    except repo.ClaimError as exc:
        # These are the customer's problem to fix, not a server fault: no
        # passengers, a duplicate claim, a negative amount.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    session.flush()
    session.refresh(claim)
    return _to_out(claim)


# Declared BEFORE /{claim_id}. FastAPI matches routes in registration order, so
# with the other order "by-reference" is tried as a UUID first and the request
# fails with a validation error instead of reaching this handler.
@router.get(
    "/by-reference/{reference}",
    response_model=ClaimOut,
    summary="Look a claim up the way a customer quotes it",
)
def read_claim_by_reference(
    reference: str, session: Annotated[Session, Depends(get_session)]
) -> ClaimOut:
    """Case- and space-insensitive, because it gets typed off a screenshot."""
    claim = repo.find_claim_by_reference(session, reference)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No claim with the reference {reference}.",
        )
    return _to_out(claim)


@router.get("/{claim_id}", response_model=ClaimOut, summary="Read a claim")
def read_claim(
    claim_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> ClaimOut:
    return _to_out(_require(session, claim_id))


@router.post(
    "/{claim_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a booking confirmation or a receipt",
)
async def upload_document(
    claim_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
    file: Annotated[UploadFile, File(description="PDF or photo, up to 10 MB.")],
    kind: Annotated[DocumentKind, Form()] = DocumentKind.RECEIPT,
    expense_id: Annotated[UUID | None, Form()] = None,
) -> DocumentUploadResponse:
    """Store one file against a claim.

    The bytes go to storage, which decides the path; the database records where
    it went and what the customer called it. The original filename is never used
    to build a path -- see app/storage/files.py.
    """
    claim = _require(session, claim_id)

    expense = None
    if expense_id is not None:
        expense = next((e for e in claim.expenses if e.id == expense_id), None)
        if expense is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That expense is not part of this claim.",
            )

    content = await file.read()
    try:
        stored = storage.save(content, content_type=file.content_type or "")
    except UploadRejected as exc:
        # 422 rather than 400: the request was well-formed, the file was not.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    try:
        document = repo.add_document(
            session,
            claim,
            kind=kind,
            original_filename=file.filename or "upload",
            stored_path=stored.path,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            expense=expense,
        )
    except repo.ClaimError as exc:
        # The bytes are already on disk; without this the file would be
        # orphaned there, invisible to the database and to any deletion request.
        storage.delete(stored.path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    return DocumentUploadResponse(
        document=_document_out(document), claim_reference=claim.reference
    )


@router.post(
    "/{claim_id}/submit", response_model=ClaimOut, summary="Submit a finished claim"
)
def submit_claim(
    claim_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> ClaimOut:
    claim = _require(session, claim_id)
    try:
        repo.submit_claim(session, claim)
    except repo.ClaimError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    session.refresh(claim)
    return _to_out(claim)


# --- helpers -----------------------------------------------------------------


def _require(session: Session, claim_id: UUID) -> Claim:
    claim = repo.get_claim(session, claim_id)
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No claim with that id."
        )
    return claim


def _format(amount: Decimal, currency: str) -> str:
    return f"{_SYMBOLS.get(currency, currency + ' ')}{amount:,.2f}"


def _document_out(document) -> DocumentOut:  # type: ignore[no-untyped-def]
    return DocumentOut(
        id=document.id,
        kind=document.kind,
        original_filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        expense_id=document.expense_id,
        created_at=document.created_at,
    )


def _to_out(claim: Claim) -> ClaimOut:
    return ClaimOut(
        id=claim.id,
        reference=claim.reference,
        status=claim.status,  # type: ignore[arg-type]
        check_id=claim.check_id,
        contact_name=claim.contact_name,
        contact_email=claim.contact_email,
        contact_phone=claim.contact_phone,
        booking_reference=claim.booking_reference,
        airline_reason=claim.airline_reason,
        cancellation_notice_days=claim.cancellation_notice_days,
        notes=claim.notes,
        passengers=[
            PassengerOut(
                id=p.id,
                full_name=p.full_name,
                national_id=p.national_id,
                is_minor=p.is_minor,
            )
            for p in claim.passengers
        ],
        expenses=[
            ExpenseOut(
                id=e.id,
                category=e.category,
                description=e.description,
                amount=str(e.amount),
                currency=e.currency,
                formatted=_format(e.amount, e.currency),
                incurred_on=e.incurred_on,
                document_count=len(e.documents),
            )
            for e in claim.expenses
        ],
        documents=[_document_out(d) for d in claim.documents],
        expense_totals={
            currency: str(total)
            for currency, total in sorted(repo.expense_totals(claim).items())
        },
        created_at=claim.created_at,
        submitted_at=claim.submitted_at,
    )
