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


# --- the CRM -----------------------------------------------------------------


class CustomerRow(BaseModel):
    """One person, as an operator needs to see them in a list.

    Everything here answers "who is this and what do I do about them". The
    evidence -- snapshots, payloads, rule outcomes -- deliberately is not:
    it belongs on the detail screen, and putting it in the list would make
    a page that takes a second to load and cannot be scanned.
    """

    check_id: UUID
    created_at: datetime

    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None

    flight_number: str
    flight_date: date

    # The check's own verdict, unchanged, plus the money. An operator sorts
    # by "is there anything here" before anything else.
    verdict: str | None
    status: str
    best_amount: str | None
    best_currency: str | None

    # Present only when they went on to file. `claim_id` is what the detail
    # button needs; the rest is what makes the row worth clicking.
    claim_id: UUID | None
    claim_reference: str | None
    claim_status: str | None
    hidden_at: datetime | None = None
    claim_submitted_at: datetime | None
    passenger_count: int
    document_count: int


class DocumentRow(BaseModel):
    """A file, described well enough to decide whether to open it."""

    id: UUID
    kind: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    # Which expense this receipt evidences, when it evidences one. A booking
    # confirmation belongs to the claim as a whole and has none.
    expense_id: UUID | None


class PassengerRow(BaseModel):
    full_name: str
    # Decrypted on the way out. The operator needs it to file with the
    # airline, which is the only reason it was ever collected.
    national_id: str | None
    is_minor: bool


class ExpenseRow(BaseModel):
    id: UUID
    category: str
    amount: str
    currency: str
    description: str | None


class CustomerDetail(CustomerRow):
    """Everything the customer actually submitted, on one screen.

    The point of the button. An operator about to write to an airline needs
    the passengers, the receipts and the two answers no database holds, and
    needs them without opening four tabs.
    """

    booking_reference: str | None
    airline_reason: str | None
    cancellation_notice: str | None
    notes: str | None

    passengers: list[PassengerRow] = []
    expenses: list[ExpenseRow] = []
    documents: list[DocumentRow] = []
    expense_totals: dict[str, str] = {}

    # Why the system decided what it decided, in the operator's hands when
    # a customer rings up to argue with it.
    result_detail: dict[str, Any] | None = None
    flight_snapshot: dict[str, Any] | None = None


class CustomerCounts(BaseModel):
    """Four numbers an operator reads before any row.

    Counted under the same rule as the list, because on the screen they are
    also the filters -- a counter that disagrees with what it filters to is
    worse than no counter.
    """

    total: int
    eligible: int
    review: int
    claims: int


class HideRequest(BaseModel):
    """Which customers to remove from the list, or put back.

    A list rather than one id per request: the screen offers multi-select,
    and fifty requests for one gesture is fifty chances for half of them to
    land.
    """

    check_ids: list[UUID] = Field(min_length=1, max_length=500)


class Moved(BaseModel):
    """How many rows actually changed.

    Not how many were asked for. If six of the fifty were already hidden,
    the honest answer is 44 -- a screen that reports the request rather
    than the outcome is one people stop believing.
    """

    moved: int


class ClaimStatusUpdate(BaseModel):
    """Where a claim has got to.

    Validated against the enum rather than taken as free text, so a typo in
    a dashboard cannot invent a ninth stage that no report counts.
    """

    status: str


class ArchivedFlightOut(BaseModel):
    """One source's record of one flight, as the archive holds it.

    Deliberately includes the DERIVED fields and the raw payload side by
    side. The question this screen answers is "did the rules get bad data
    or make a bad decision", and that can only be settled by seeing both
    what the source said and what we made of it.
    """

    provider: str
    observed_at: datetime
    is_final: bool

    flight_number: str
    flight_date: date
    airline_iata: str | None
    origin_iata: str | None
    destination_iata: str | None
    status: str

    scheduled_departure: datetime | None
    actual_departure: datetime | None
    scheduled_arrival: datetime | None
    actual_arrival: datetime | None

    departure_delay_minutes: float | None
    arrival_delay_minutes: float | None

    usable: bool
    unusable_reason: str | None
    distance_km: float | None

    raw: dict[str, Any]


class ArchivedFlightPage(BaseModel):
    items: list[ArchivedFlightOut]
    # Not a total. Counting every matching flight means decoding every
    # stored payload, which is the expensive thing this endpoint avoids --
    # so it says "there are more" rather than inventing a number it did
    # not actually compute.
    truncated: bool
