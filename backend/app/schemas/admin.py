"""Response shapes for the admin API.

These are a different view of the same rows the customer endpoints serve. They
carry more -- contact details, the raw provider payload, every passenger's
identity number -- which is exactly why the endpoints behind them are guarded.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A page of results, with the total behind it.

    `total` is what makes a list usable: without it nobody can tell whether
    "50 results" means fifty or the first fifty of nine thousand.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class CheckRow(BaseModel):
    """One check, as a row in the operator's list."""

    id: UUID
    created_at: datetime
    flight_number: str
    flight_date: date
    contact_name: str | None
    contact_email: str | None
    status: str
    verdict: str | None
    # The one line that says what a human needs to do about this row. A review
    # queue nobody can skim is a review queue nobody works.
    message: str | None
    best_regulation: str | None
    best_amount: str | None
    best_currency: str | None
    provider: str
    has_claim: bool


class CheckDetail(CheckRow):
    """One check, opened.

    Carries the full evidence: the facts the verdict was computed from, every
    regulation's reasoning, and the untouched provider payload. That last one
    is what lets a disputed verdict be re-explained months later.
    """

    flight_snapshot: dict[str, Any] | None
    result_detail: dict[str, Any] | None
    provider_payload: dict[str, Any] | None
    others_on_this_flight: list[CheckRow] = Field(
        default_factory=list,
        description=(
            "Everyone else who checked this flight. They usually belong in one "
            "claim: cheaper to run and far stronger against the airline than "
            "the same facts argued five times."
        ),
    )


class ClaimRow(BaseModel):
    id: UUID
    reference: str
    created_at: datetime
    submitted_at: datetime | None
    status: str
    contact_name: str
    contact_email: str
    flight_number: str
    flight_date: date
    verdict: str | None
    best_amount: str | None
    best_currency: str | None
    passenger_count: int
    expense_count: int
    document_count: int
    expense_totals: dict[str, str]


class Summary(BaseModel):
    """The numbers an operator looks at in the morning."""

    checks_total: int
    checks_by_verdict: dict[str, int]
    checks_by_status: dict[str, int]
    claims_total: int
    claims_by_status: dict[str, int]
    # Per currency, never one figure. Euro, pounds and shekels do not add up,
    # and a single "pipeline value" would be a number nobody could defend.
    eligible_value_by_currency: dict[str, str]
    needs_review: int = Field(description="The size of the queue right now.")
