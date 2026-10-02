"""Reading the archive back as a screen.

WHY THESE TESTS AND NOT OTHERS

This is a diagnostic tool, so its failure mode is specific and nasty: it
can be WRONG IN A REASSURING DIRECTION. A query that quietly drops rows
tells an operator "we have no record of that flight" when the record is
sitting in the table, and they will go and tell a customer the same
thing.

So the tests here are mostly about completeness -- that a flight is found
whatever shape its record is in -- rather than about formatting.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.db import flights as repo
from app.db.models import FlightLookup
from app.db.session import (
    create_all,
    create_db_engine,
    create_session_factory,
    session_scope,
)

SEP_26 = date(2026, 9, 26)


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    with session_scope(create_session_factory(engine)) as session:
        yield session


def _store(
    session: Session,
    *,
    number: str = "BZ887",
    flight_date: date = SEP_26,
    provider: str = "iaa",
    origin: str | None = "JMK",
    destination: str | None = "TLV",
    status: str = "LANDED",
    sched_dep: str | None = None,
    actual_dep: str | None = None,
    sched_arr: str | None = "2026-09-26T10:50:00+00:00",
    actual_arr: str | None = "2026-09-26T12:18:00+00:00",
) -> None:
    session.add(
        FlightLookup(
            provider=provider,
            flight_number=number,
            flight_date=flight_date,
            observed_at=datetime(2026, 9, 26, 13, 0, tzinfo=UTC),
            is_final=True,
            flights=[
                {
                    "flight_number": number,
                    "flight_date": flight_date.isoformat(),
                    "status": status,
                    "provider": provider,
                    "airline_iata": number[:2],
                    "origin_iata": origin,
                    "destination_iata": destination,
                    "scheduled_departure": sched_dep,
                    "actual_departure": actual_dep,
                    "scheduled_arrival": sched_arr,
                    "actual_arrival": actual_arr,
                    "raw": {"CHOPER": number[:2], "CHRMINE": status},
                }
            ],
        )
    )
    session.flush()


def test_a_flight_number_is_found_across_the_whole_archive(
    session: Session,
) -> None:
    """Searching a number is not bounded by dates, deliberately.

    The reason somebody types a flight number into a troubleshooting
    screen is that something went wrong, and they rarely know which day it
    was. Making them guess the date first turns one lookup into several.
    """
    _store(session, flight_date=date(2026, 3, 30))
    _store(session, flight_date=date(2026, 9, 26))

    found, _ = repo.search_flights(session, number="BZ887")

    assert len(found) == 2
    assert [f.flight_date for f in found] == [date(2026, 9, 26), date(2026, 3, 30)]


def test_the_number_is_matched_case_and_space_insensitively(
    session: Session,
) -> None:
    """Somebody reading a flight number off a boarding pass types it
    however it is printed. ` bz887 ` is the same flight."""
    _store(session, number="BZ887")

    found, _ = repo.search_flights(session, number="  bz887 ")

    assert len(found) == 1


def test_both_sources_are_shown_separately_and_not_merged(
    session: Session,
) -> None:
    """THE WHOLE POINT OF THE SCREEN.

    When the board and the commercial feed disagree, merging them hides
    the disagreement -- and the disagreement is usually the bug. 6H502
    was diagnosed precisely by seeing that the board had an arrival pair
    and AeroDataBox had a departure time and no arrival airport.
    """
    _store(session, provider="iaa")
    _store(session, provider="aerodatabox", destination=None)

    found, _ = repo.search_flights(session, number="BZ887")

    assert {f.provider for f in found} == {"iaa", "aerodatabox"}


def test_a_record_the_rules_cannot_use_says_why(session: Session) -> None:
    """The field that answers "why did it say it could not find my flight".

    A record can be present and complete-looking and still unusable -- no
    arrival airport is the common one. Without this the screen would show
    a perfectly reasonable row next to a customer complaining, and the
    contradiction would send somebody into the rules engine looking for a
    bug that is not there.
    """
    _store(session, destination=None)

    found, _ = repo.search_flights(session, number="BZ887")

    assert found[0].usable is False
    assert found[0].unusable_reason


def test_a_flight_with_no_times_at_all_does_not_crash_the_sort(
    session: Session,
) -> None:
    """A cancellation the board publishes with no times.

    The sort key fell back to `datetime.min`, which is naive, while every
    stored time is timezone-aware -- and Python refuses to compare the
    two. ONE such row would have raised TypeError and taken out the whole
    page, including the fifty rows that were fine.
    """
    _store(session, status="CANCELLED", sched_arr=None, actual_arr=None)
    _store(session, number="LY325", sched_arr="2026-09-26T08:00:00+00:00")

    found, _ = repo.search_flights(session, on=SEP_26)

    assert len(found) == 2


def test_browsing_finds_disruptions_rather_than_the_newest_rows(
    session: Session,
) -> None:
    """The bug the first version shipped with.

    The scan was capped at 400 rows BEFORE the disruption filter ran. Sorted
    newest-first, those 400 were future scheduled flights -- none of which
    can be disrupted yet -- so a week containing real cancellations
    reported nothing at all.

    A limit applied before a filter is a limit on the wrong thing.
    """
    # Lots of future, undisrupted flights, and one real cancellation behind
    # them.
    for i in range(30):
        _store(
            session,
            number=f"XX{i:03d}",
            flight_date=date(2026, 10, 5),
            status="SCHEDULED",
            sched_arr="2026-10-05T10:00:00+00:00",
            actual_arr=None,
        )
    _store(
        session,
        number="EK2168",
        flight_date=date(2026, 10, 1),
        status="CANCELLED",
        sched_arr=None,
        actual_arr=None,
    )

    # The date range is the real bound, so the cancellation is found.
    found, truncated = repo.search_flights(
        session,
        since=date(2026, 9, 28),
        until=date(2026, 10, 6),
        disrupted_only=True,
    )

    assert [f.flight_number for f in found] == ["EK2168"], (
        "the cancellation sits behind thirty newer, undisrupted rows"
    )
    assert truncated is False


def test_a_scan_cut_short_says_so_instead_of_reporting_nothing(
    session: Session,
) -> None:
    """The honest half of the same problem.

    The scan cap has to sit BEFORE the disruption filter -- the filter
    needs the decoded payload -- so a cap that bites really does drop
    matching flights. It cannot be made not to.

    What it can do is admit it. On a screen whose entire job is answering
    "do we have this flight?", an incomplete answer that looks complete is
    the worst possible output: somebody reads an empty list and tells a
    customer we have no record.
    """
    for i in range(30):
        _store(
            session,
            number=f"XX{i:03d}",
            flight_date=date(2026, 10, 5),
            status="SCHEDULED",
            sched_arr="2026-10-05T10:00:00+00:00",
            actual_arr=None,
        )
    _store(
        session,
        number="EK2168",
        flight_date=date(2026, 10, 1),
        status="CANCELLED",
        sched_arr=None,
        actual_arr=None,
    )

    found, truncated = repo.search_flights(
        session,
        since=date(2026, 9, 28),
        until=date(2026, 10, 6),
        disrupted_only=True,
        max_scan=10,
    )

    assert found == [], "the cancellation really is beyond the cap"
    assert truncated is True, "and the caller must be told the answer is partial"


def test_a_short_delay_counts_as_a_disruption_but_an_on_time_flight_does_not(
    session: Session,
) -> None:
    """Fifteen minutes, which is below every legal threshold.

    The browse list answers "what happened today", not "what is payable" --
    the rules decide the second question. A list that showed only the
    three-hour delays would hide the pattern that something is going wrong
    at an airline long before any single flight qualifies.
    """
    _store(
        session,
        number="ON1",
        sched_arr="2026-09-26T10:00:00+00:00",
        actual_arr="2026-09-26T10:05:00+00:00",
    )
    _store(
        session,
        number="LATE1",
        sched_arr="2026-09-26T10:00:00+00:00",
        actual_arr="2026-09-26T10:40:00+00:00",
    )

    found, _ = repo.search_flights(session, on=SEP_26, disrupted_only=True)

    assert [f.flight_number for f in found] == ["LATE1"]


def test_truncation_is_reported_rather_than_hidden(session: Session) -> None:
    """A cut-off list that does not say so is how somebody concludes a
    flight is missing when it is merely further down."""
    for i in range(5):
        _store(session, number=f"BZ{i:03d}", sched_arr="2026-09-26T10:00:00+00:00")

    found, truncated = repo.search_flights(session, on=SEP_26, limit=3)

    assert len(found) == 3
    assert truncated is True


def test_the_raw_payload_comes_back_untouched(session: Session) -> None:
    """The last word in any argument about the data.

    Derived fields are our reading of the source; the raw payload is what
    the source actually said. Every data bug in this project has been
    settled by comparing the two, so the screen has to carry both.
    """
    _store(session)

    found, _ = repo.search_flights(session, number="BZ887")

    assert found[0].raw == {"CHOPER": "BZ", "CHRMINE": "LANDED"}
