"""One row per customer, for the operator's screen.

WHY THIS IS A JOIN AND NOT A NEW TABLE

A customer is not stored anywhere in this system, and deliberately so. What
is stored is what they DID: an `eligibility_checks` row when they asked
about a flight, and a `claims` row if they went on to file. A person who was
turned away has the first and never the second.

So "the customer list" is a question about two tables, and the honest way to
answer it is to ask both. The alternative -- a `customers` table kept in step
by a listener, a trigger or a background job -- introduces a second copy of
facts that are already written down, and a second copy can be stale, can be
missing rows, and can disagree with the first. It would be a worse answer to
the question "have we captured everything?", not a better one, because the
answer would depend on whether some process was running.

This query cannot be stale. It reads the rows the application just wrote.

WHAT COUNTS AS A CUSTOMER

A check with no name and no email is somebody typing a flight number to see
what happens. There is nobody to call and nothing to follow up, and putting
thousands of them in an operator's list would bury the people who did leave
their details. So by default a row appears when we have a way to reach
somebody, or when they filed a claim -- and `include_anonymous` shows the
rest, because "how many people looked and left" is a real question, just a
different one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Claim, Document, EligibilityCheck, Passenger


@dataclass(frozen=True, slots=True)
class CustomerRecord:
    """A check, and the claim it turned into if it turned into one.

    A plain object rather than a tuple so the caller reads
    `record.claim is None` instead of `record[1] is None`, which is the
    difference between code that can be reviewed and code that cannot.
    """

    check: EligibilityCheck
    claim: Claim | None

    @property
    def contact_name(self) -> str | None:
        """The claim's name wins: it was typed later and more deliberately.

        Somebody who files a claim fills in their full legal name, because
        it goes to an airline. The name on the original check may be a
        first name typed quickly. Falling back to the check matters for
        everybody who was refused and never filed.
        """
        return (self.claim.contact_name if self.claim else None) or self.check.contact_name

    @property
    def contact_email(self) -> str | None:
        return (self.claim.contact_email if self.claim else None) or self.check.contact_email

    @property
    def contact_phone(self) -> str | None:
        """Only ever collected on the claim form.

        A refused customer is never asked for a phone number -- there is
        nothing to ring them about -- so this is None for most rows, and
        that is correct rather than missing data.
        """
        return self.claim.contact_phone if self.claim else None


def _is_a_customer() -> ColumnElement[bool]:
    """Somebody we could actually contact, or who filed.

    Defined once because the LIST and the COUNTERS both need it, and the
    counters double as filters on the screen -- a number that disagrees with
    the list it filters to is worse than showing no number at all. Sharing
    the predicate is what makes them move together.
    """
    return or_(
        EligibilityCheck.contact_email.is_not(None),
        EligibilityCheck.contact_name.is_not(None),
        Claim.id.is_not(None),
    )


def _base(include_anonymous: bool) -> Select[tuple[EligibilityCheck, Claim | None]]:
    """Every check, with its claim attached when there is one.

    An OUTER join, which is the whole design: an INNER join would silently
    drop every customer who was told no, and those are the majority and the
    ones most likely to be worth a second look when a rule changes.
    """
    stmt = (
        select(EligibilityCheck, Claim)
        .outerjoin(Claim, Claim.check_id == EligibilityCheck.id)
        .options(
            joinedload(Claim.passengers),
            joinedload(Claim.documents),
        )
    )
    if not include_anonymous:
        stmt = stmt.where(_is_a_customer())
    return stmt


def _filtered(
    stmt: Select[tuple[EligibilityCheck, Claim | None]],
    *,
    verdict: str | None,
    search: str | None,
    has_claim: bool | None,
) -> Select[tuple[EligibilityCheck, Claim | None]]:
    if verdict:
        stmt = stmt.where(EligibilityCheck.verdict == verdict)
    if has_claim is True:
        stmt = stmt.where(Claim.id.is_not(None))
    elif has_claim is False:
        stmt = stmt.where(Claim.id.is_(None))
    if search:
        # One box, because an operator looking somebody up has ONE thing in
        # hand -- an email from a reply, a flight number from a phone call,
        # a name. Making them choose which field it is first is a worse
        # version of the same search.
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(EligibilityCheck.contact_email).like(like),
                func.lower(EligibilityCheck.contact_name).like(like),
                func.lower(EligibilityCheck.flight_number).like(like),
                func.lower(Claim.contact_email).like(like),
                func.lower(Claim.contact_name).like(like),
                func.lower(Claim.reference).like(like),
            )
        )
    return stmt


def list_customers(
    session: Session,
    *,
    verdict: str | None = None,
    search: str | None = None,
    has_claim: bool | None = None,
    include_anonymous: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[CustomerRecord]:
    """The operator's list, newest first.

    Newest first is not a default chosen for want of anything better: the
    work arrives at the top. Somebody who checked a flight ten minutes ago
    is who an operator is looking for when they open this screen.
    """
    stmt = _filtered(
        _base(include_anonymous), verdict=verdict, search=search, has_claim=has_claim
    )
    rows = session.execute(
        stmt.order_by(EligibilityCheck.created_at.desc()).limit(limit).offset(offset)
    ).unique()
    return [CustomerRecord(check=check, claim=claim) for check, claim in rows]


def count_customers(
    session: Session,
    *,
    verdict: str | None = None,
    search: str | None = None,
    has_claim: bool | None = None,
    include_anonymous: bool = False,
) -> int:
    """How many rows the filters match, ignoring the page.

    Without this the screen can say "50 customers" when it means "the first
    50", and an operator who pages to the end has no idea whether they have
    seen everybody. For a list whose purpose is not missing anyone, that is
    the number that matters most.
    """
    stmt = _filtered(
        _base(include_anonymous), verdict=verdict, search=search, has_claim=has_claim
    )
    # Count the checks, not the joined rows. A check has at most one claim,
    # so they agree today -- but `count(*)` over a join is the classic way to
    # start double-counting the moment a one-to-many relationship appears.
    return session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0


def documents_for_claim(session: Session, claim_id: uuid.UUID) -> list[Document]:
    """Every file attached to one claim, oldest first.

    Oldest first here, unlike the customer list: these are read as a set
    rather than scanned for the newest, and upload order is the order the
    customer sent them, which is usually the order they make sense in.
    """
    return list(
        session.scalars(
            select(Document)
            .where(Document.claim_id == claim_id)
            .order_by(Document.created_at)
        )
    )


def passenger_count(session: Session, claim_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Passenger)
            .where(Passenger.claim_id == claim_id)
        )
        or 0
    )


def first_checked_on(session: Session) -> date | None:
    """The oldest check we hold, for the screen's "since" line."""
    value = session.scalar(select(func.min(EligibilityCheck.created_at)))
    return value.date() if value else None


def customer_counts(
    session: Session, *, include_anonymous: bool = False
) -> dict[str, int]:
    """The shape of the day, in one query.

    Aggregated in SQL rather than by walking the rows in Python: the whole
    point of a counter is that it stays instant when the table does not, and
    counting ten thousand ORM objects to display four numbers would make the
    screen slower the more successful the business gets.

    The same `_is_a_customer` predicate as the list, so the counters and the
    rows beneath them can never tell different stories.
    """
    pays = EligibilityCheck.verdict.in_(("ELIGIBLE", "LIKELY_ELIGIBLE"))
    stmt = (
        select(
            func.count().label("total"),
            func.count().filter(pays).label("eligible"),
            func.count()
            .filter(EligibilityCheck.verdict == "NEEDS_REVIEW")
            .label("review"),
            func.count(Claim.id).label("claims"),
        )
        .select_from(EligibilityCheck)
        .outerjoin(Claim, Claim.check_id == EligibilityCheck.id)
    )
    if not include_anonymous:
        stmt = stmt.where(_is_a_customer())

    row = session.execute(stmt).one()
    return {
        "total": row.total or 0,
        "eligible": row.eligible or 0,
        "review": row.review or 0,
        "claims": row.claims or 0,
    }
