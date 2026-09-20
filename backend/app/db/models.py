"""The eligibility_checks table.

Every check is recorded, eligible or not. You asked for that, and it is also the
most commercially valuable table in the system: a list of people with a flight
problem and a reason to come back.

Two columns deserve explanation, because they are the reason this table is
worth more than a log line.

`flight_snapshot` stores the normalised facts the verdict was computed from.
`provider_payload` stores what the provider actually said, untouched. Together
they mean a decision can be re-explained months later, and -- if a rule turns
out to have been wrong -- every historical check can be re-run against the
corrected rule without paying for a single lookup again. Deleting a bad verdict
is easy; recovering the evidence behind it is not.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from enum import StrEnum

from app.db.types import EncryptedText, MoneyAmount, UtcDateTime, utc_now


class Base(DeclarativeBase):
    """Declarative base for every table in the system."""


class EligibilityCheck(Base):
    """One customer asking one question about one flight."""

    __tablename__ = "eligibility_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, nullable=False, index=True
    )

    # --- what was asked ---
    flight_number: Mapped[str] = mapped_column(String(10), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)

    # --- who asked ---
    #
    # Optional, because the first thing a visitor does is check a flight, and
    # demanding a name before answering would lose most of them. The claim form
    # collects it properly once there is something worth claiming.
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320), index=True)

    # --- what we answered ---
    #
    # `status` is the kind of answer (DECIDED / NOT_FOUND / AMBIGUOUS /
    # UNRESOLVED); `verdict` is what a DECIDED answer said. Both are stored as
    # plain strings rather than a database enum: the set of values will grow,
    # and on PostgreSQL an enum change is a migration with a table lock.
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    verdict: Mapped[str | None] = mapped_column(String(20), index=True)
    message: Mapped[str | None] = mapped_column(String(2000))

    # --- the money, where there is any ---
    best_regulation: Mapped[str | None] = mapped_column(String(20))
    best_amount: Mapped[Decimal | None] = mapped_column(MoneyAmount)
    best_currency: Mapped[str | None] = mapped_column(String(3))

    # --- the evidence ---
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    flight_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        # The two queries this table will actually serve: "show me everything
        # for this flight" (several passengers check the same one, and they
        # should become one claim) and "show me what needs a human, oldest
        # first" (the review queue).
        Index("ix_checks_flight", "flight_number", "flight_date"),
        Index("ix_checks_review_queue", "verdict", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<EligibilityCheck {self.flight_number} {self.flight_date} "
            f"{self.verdict or self.status}>"
        )


# --- Claims ------------------------------------------------------------------
#
# A check answers "am I owed anything?". A claim is what happens next: the
# passenger details, the booking, and the out-of-pocket costs that get
# reimbursed on top of the fixed compensation.
#
# Four tables rather than more columns on eligibility_checks, because one check
# becomes one claim covering several passengers with many receipts. Flattening
# that into a single row means either JSON blobs nobody can query or a great
# many empty columns.


class ClaimStatus(StrEnum):
    """Where a claim is in its life.

    Stored as a string rather than a database enum: this list will grow, and on
    PostgreSQL adding a value to an enum type is a migration with a table lock.
    """

    DRAFT = "DRAFT"  # started, not yet submitted
    SUBMITTED = "SUBMITTED"  # the customer is done
    IN_REVIEW = "IN_REVIEW"  # we are checking it
    SENT_TO_AIRLINE = "SENT_TO_AIRLINE"
    AWAITING_AIRLINE = "AWAITING_AIRLINE"
    SETTLED = "SETTLED"  # paid
    REJECTED = "REJECTED"  # the airline said no
    WITHDRAWN = "WITHDRAWN"  # the customer pulled out


class ExpenseCategory(StrEnum):
    """What the money was spent on.

    A fixed list rather than free text, because the whole point of collecting
    expenses is to total them and to argue they were reasonable -- neither of
    which works if one person writes "taxi" and the next writes "Uber home".
    """

    MEAL = "MEAL"
    DRINK = "DRINK"
    HOTEL = "HOTEL"
    TRANSPORT = "TRANSPORT"  # taxis, trains, parking
    COMMUNICATION = "COMMUNICATION"  # the calls the airline owes you
    REBOOKING = "REBOOKING"  # a replacement ticket bought at your own cost
    OTHER = "OTHER"


class DocumentKind(StrEnum):
    BOOKING = "BOOKING"  # the original ticket or confirmation
    BOARDING_PASS = "BOARDING_PASS"
    RECEIPT = "RECEIPT"  # evidence for one expense
    IDENTIFICATION = "IDENTIFICATION"
    CORRESPONDENCE = "CORRESPONDENCE"  # what the airline wrote back
    OTHER = "OTHER"


class Claim(Base):
    """One passenger group pursuing one disrupted flight."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Human-readable and quotable. Customers ring up and read this out; nobody
    # reads out a UUID, and nobody should have to.
    reference: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True
    )

    # The check this grew out of. Unique: one check produces at most one claim,
    # and the check carries the verdict, the flight snapshot and the reasoning,
    # so none of that is copied here where it could drift.
    check_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eligibility_checks.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ClaimStatus.DRAFT.value, index=True
    )

    # --- what the customer tells us ---
    booking_reference: Mapped[str | None] = mapped_column(String(20))
    contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40))

    # The two questions no flight database can answer, asked of the person who
    # was actually there. `airline_reason` decides whether the disruption was
    # within the airline's control; `cancellation_notice` decides whether a
    # cancellation is payable at all.
    airline_reason: Mapped[str | None] = mapped_column(Text)
    cancellation_notice: Mapped[str | None] = mapped_column(String(20))

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    # When the confirmation email went. Its absence is what makes sending
    # idempotent: a retried request or a replayed background task cannot send
    # the same confirmation twice, and a customer who receives it three times
    # stops trusting the next email we send -- which is the one telling them
    # the airline paid. Left NULL on a failed send, so a retry can pick it up.
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    check: Mapped[EligibilityCheck] = relationship(lazy="joined")
    passengers: Mapped[list[Passenger]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin"
    )
    expenses: Mapped[list[Expense]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_claims_queue", "status", "created_at"),)

    def __repr__(self) -> str:
        return f"<Claim {self.reference} {self.status}>"


class Passenger(Base):
    """One person on the booking.

    Compensation is per passenger, so a family of four on one booking is four
    times the award -- which is exactly why this is a table and not a name field
    on the claim.
    """

    __tablename__ = "passengers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # A national identity number: sensitive personal data under both the GDPR
    # and Israeli privacy law, and the one field here that is worth stealing.
    #
    # Encrypted at rest by the column type, so the database file holds
    # ciphertext and has never held anything else. Code above this layer reads
    # and writes the number itself and does not know the difference -- which is
    # the point, because anything that has to be remembered eventually is not.
    #
    # Still outstanding: a retention policy. A claim that settled in 2027 has
    # no business still holding an ID number in 2031, and encryption is not an
    # answer to keeping data longer than there is a reason to.
    national_id: Mapped[str | None] = mapped_column(EncryptedText)
    is_minor: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, nullable=False
    )

    claim: Mapped[Claim] = relationship(back_populates="passengers")

    def __repr__(self) -> str:
        return f"<Passenger {self.full_name}>"


class Expense(Base):
    """One out-of-pocket cost caused by the disruption.

    Reimbursed at cost against a receipt, unlike the fixed compensation -- which
    is why the amount lives here rather than being computed by any rule.
    """

    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )

    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    # In whatever currency it was actually paid in. A hotel bill in Frankfurt is
    # in euro whatever currency the compensation is awarded in, and converting
    # it here would destroy the only number the receipt actually proves.
    amount: Mapped[Decimal] = mapped_column(MoneyAmount, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    incurred_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, nullable=False
    )

    claim: Mapped[Claim] = relationship(back_populates="expenses")
    documents: Mapped[list[Document]] = relationship(
        back_populates="expense", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Expense {self.category} {self.amount} {self.currency}>"


class Document(Base):
    """An uploaded file: the booking, a boarding pass, a receipt.

    The row records where the file is and what it is. The bytes live in storage
    -- local disk now, object storage later -- so `stored_path` is deliberately
    opaque to everything except the storage layer.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A receipt belongs to the expense it evidences. Nullable because a booking
    # confirmation or a boarding pass evidences the claim as a whole.
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # What the customer called it. Kept for their benefit, never used to build a
    # path: a filename from a browser is attacker-controlled input.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, nullable=False
    )

    claim: Mapped[Claim] = relationship(back_populates="documents")
    expense: Mapped[Expense | None] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document {self.kind} {self.original_filename}>"


class FlightLookup(Base):
    """One source's answer about one flight number on one date, kept.

    TWO JOBS, ONE TABLE, and they are the same job seen from either end.

    As a CACHE it stops us paying twice for one fact. A cancelled flight has a
    hundred and eighty passengers, and if any of them tell each other about us,
    they check the same number and the same date within a day of each other.
    Without this, that is a hundred and eighty identical purchases of one
    answer.

    As an ARCHIVE it outlives the source. The Ben Gurion board publishes a
    rolling five days and the commercial feed reaches back a year at most --
    while a passenger can claim for four years in Israel and six in the UK. No
    subscription closes that gap, at any price. Recording what we see, on the
    day we see it, is the only thing that does: a row written today still
    answers a question asked in 2030.

    Keyed by (provider, flight_number, flight_date) rather than by flight,
    because that is the question asked. One number on one date can legitimately
    be several flights -- a daily rotation crossing midnight, a route flown
    twice -- and the answer to "what flew as BA242 that day" is the whole list,
    including when the list is empty.
    """

    __tablename__ = "flight_lookups"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "flight_number",
            "flight_date",
            name="uq_flight_lookups_question",
        ),
        # The lookup every read does.
        Index("ix_flight_lookups_question", "flight_number", "flight_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which source said so. Kept in the key, not just as a note: two sources
    # genuinely disagree about the same flight -- the board has cancellations
    # the feed drops, the feed has landing times the board never learns -- and
    # merging them into one row would lose whichever was written second.
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    flight_number: Mapped[str] = mapped_column(String(10), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)

    observed_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, nullable=False, index=True
    )

    # True when every flight in the payload has finished: landed, cancelled or
    # diverted. Those cannot change again, so the row is good forever. A
    # scheduled or airborne flight is a prediction wearing the same shape, and
    # serving yesterday's prediction as today's fact is how a delayed flight
    # gets recorded as punctual.
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # The provider's answer as RawFlight records, not as vendor JSON. Vendor
    # JSON would tie every future read to a schema we do not control and cannot
    # re-parse once the adapter has moved on; RawFlight is our own shape and
    # the thing the rest of the system actually consumes.
    #
    # An empty list is a real answer: "that flight is not in our data".
    flights: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:
        return (
            f"<FlightLookup {self.provider} {self.flight_number} "
            f"{self.flight_date} final={self.is_final}>"
        )
