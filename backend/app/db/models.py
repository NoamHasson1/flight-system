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

from sqlalchemy import JSON, Date, Index, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import MoneyAmount, UtcDateTime, utc_now


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
