"""Request and response shapes for claims."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models import ClaimStatus, DocumentKind, ExpenseCategory


class PassengerIn(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    # Optional: children often have none, and demanding one would block the
    # claim of the person least able to argue about it.
    national_id: str | None = Field(default=None, max_length=40)
    is_minor: bool = False


class ExpenseIn(BaseModel):
    category: ExpenseCategory
    # A string, not a float. The same refusal Money makes: a float that reaches
    # us has already lost precision, and accepting one would launder the error.
    amount: str = Field(..., examples=["180.00"])
    currency: str = Field(..., min_length=3, max_length=3, examples=["EUR"])
    description: str | None = Field(default=None, max_length=500)
    incurred_on: date | None = None

    @field_validator("amount")
    @classmethod
    def _positive_decimal(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError(f"{value!r} is not an amount") from None
        if amount <= 0:
            raise ValueError("an expense must be a positive amount")
        if amount > Decimal("100000"):
            # Not a rule, a typo guard: 18000 entered instead of 180.00 is a
            # far commoner event than a genuine six-figure taxi fare.
            raise ValueError("that amount looks like a mistake; please check it")
        return value

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()


class ClaimCreate(BaseModel):
    check_id: UUID = Field(description="From the eligibility check.")
    contact_name: str = Field(..., min_length=1, max_length=200)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None, max_length=40)
    booking_reference: str | None = Field(default=None, max_length=20)

    # The two questions no flight database can answer. Both decide eligibility
    # and both can only come from the person who was actually there.
    airline_reason: str | None = Field(
        default=None,
        max_length=2000,
        description="What reason the airline gave, in the customer's own words.",
    )
    cancellation_notice_days: int | None = Field(
        default=None,
        ge=0,
        le=365,
        description="For a cancellation: how many days' notice they were given.",
    )

    passengers: list[PassengerIn] = Field(default_factory=list)
    expenses: list[ExpenseIn] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)


class PassengerOut(BaseModel):
    id: UUID
    full_name: str
    national_id: str | None
    is_minor: bool


class ExpenseOut(BaseModel):
    id: UUID
    category: str
    description: str | None
    amount: str
    currency: str
    formatted: str
    incurred_on: date | None
    document_count: int


class DocumentOut(BaseModel):
    id: UUID
    kind: str
    original_filename: str
    content_type: str
    size_bytes: int
    expense_id: UUID | None
    created_at: datetime


class ClaimOut(BaseModel):
    id: UUID
    reference: str = Field(
        description="Quote this. It is what a customer reads out on the phone.",
        examples=["FS-2026-K7M9QX"],
    )
    status: ClaimStatus
    check_id: UUID

    contact_name: str
    contact_email: str
    contact_phone: str | None
    booking_reference: str | None
    airline_reason: str | None
    cancellation_notice_days: int | None
    notes: str | None

    passengers: list[PassengerOut]
    expenses: list[ExpenseOut]
    documents: list[DocumentOut]

    # Per currency, never one number. A hotel in euro and a taxi in shekels do
    # not add up, and inventing a rate to make them would be making up a figure
    # somebody later has to defend to an airline.
    expense_totals: dict[str, str] = Field(
        description="Total expenses per currency, as exact decimal strings.",
        examples=[{"EUR": "226.20", "ILS": "240.50"}],
    )

    created_at: datetime
    submitted_at: datetime | None


class DocumentUploadResponse(BaseModel):
    document: DocumentOut
    claim_reference: str


__all__ = [
    "ClaimCreate",
    "ClaimOut",
    "DocumentKind",
    "DocumentOut",
    "DocumentUploadResponse",
    "ExpenseIn",
    "ExpenseOut",
    "PassengerIn",
    "PassengerOut",
]
