"""The nightly snapshot of the Ben Gurion board.

This job exists because of a gap nobody sells a way out of: a passenger can
claim for four years in Israel, the commercial feed reaches back one at most,
and the board itself publishes five days. The only way to have 2023 in four
years' time is to have written it down in 2023.

So the tests here are about durability rather than cleverness. Can it be run
twice without damage; does a later, worse answer overwrite a better one; does a
flight written today come back tomorrow through the ordinary cache path.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import FlightLookup
from app.db.session import create_all, create_db_engine, create_session_factory
from app.domain.models import FlightStatus
from app.providers.base import RawFlight
from app.providers.cache import CachingProvider
from app.tasks.archive_board import fold_in

WHEN = date(2026, 9, 18)


@pytest.fixture
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    return create_session_factory(engine)


def _flight(number: str, status: FlightStatus, **overrides: object) -> RawFlight:
    base: dict[str, object] = {
        "flight_number": number,
        "flight_date": WHEN,
        "status": status,
        "provider": "iaa",
        "airline_iata": number[:2],
        "origin_iata": "TLV",
        "destination_iata": "HER",
        "scheduled_departure": datetime(2026, 9, 18, 5, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return RawFlight(**base)  # type: ignore[arg-type]


class Board:
    """A stand-in for the live board."""

    name = "iaa"

    def __init__(self, flights: Sequence[RawFlight]) -> None:
        self._flights = tuple(flights)
        self.calls = 0

    async def fetch(self, flight_number: str, flight_date: date) -> Sequence[RawFlight]:
        self.calls += 1
        return tuple(
            f
            for f in self._flights
            if f.flight_number == flight_number.upper() and f.flight_date == flight_date
        )


# --- Writing -----------------------------------------------------------------


def test_one_row_per_question_not_per_flight(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Two flights sharing a number on a date are ONE answer.

    "What flew as BZ734 that day" is the question a customer asks, and the
    honest answer is both of them. Splitting them into two rows would let a
    later read find one and confidently report it as the flight.
    """
    written = fold_in(
        session_factory,
        "iaa",
        [
            _flight("BZ734", FlightStatus.LANDED),
            _flight("BZ734", FlightStatus.LANDED, destination_iata="ATH"),
            _flight("LY315", FlightStatus.LANDED),
        ],
    )

    assert written == 2
    with session_factory() as session:
        rows = session.scalars(select(FlightLookup)).all()
        assert len(rows) == 2
        by_number = {r.flight_number: r for r in rows}
        assert len(by_number["BZ734"].flights) == 2
        assert len(by_number["LY315"].flights) == 1


def test_running_it_twice_changes_nothing(session_factory) -> None:  # type: ignore[no-untyped-def]
    """It runs unattended on a timer. A retry, an overlap, a double-fire from a
    restarted scheduler -- none of them may duplicate or corrupt a row."""
    flights = [_flight("BZ734", FlightStatus.LANDED)]
    fold_in(session_factory, "iaa", flights)
    fold_in(session_factory, "iaa", flights)

    with session_factory() as session:
        assert len(session.scalars(select(FlightLookup)).all()) == 1


def test_a_settled_flight_is_never_degraded(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The rule the whole archive rests on.

    Tomorrow's board will not contain today's flight -- the window will have
    rolled past it. If a later run could overwrite a landed flight with
    whatever it knows now, the archive would never accumulate anything: it
    would always be exactly as thin as the most recent snapshot.
    """
    fold_in(session_factory, "iaa", [_flight("BZ734", FlightStatus.LANDED)])
    fold_in(
        session_factory,
        "iaa",
        [_flight("BZ734", FlightStatus.SCHEDULED, actual_departure=None)],
    )

    with session_factory() as session:
        row = session.scalar(select(FlightLookup))
        assert row is not None
        assert row.is_final is True
        assert row.flights[0]["status"] == "LANDED"


def test_an_unsettled_flight_is_updated_until_it_settles(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The other half: a flight seen as scheduled this morning and landed
    tonight must end up stored as landed."""
    fold_in(session_factory, "iaa", [_flight("BZ734", FlightStatus.SCHEDULED)])
    fold_in(
        session_factory,
        "iaa",
        [
            _flight(
                "BZ734",
                FlightStatus.LANDED,
                actual_departure=datetime(2026, 9, 18, 13, 0, tzinfo=UTC),
            )
        ],
    )

    with session_factory() as session:
        row = session.scalar(select(FlightLookup))
        assert row is not None
        assert row.is_final is True
        assert row.flights[0]["status"] == "LANDED"


# --- Reading it back ---------------------------------------------------------


async def test_an_archived_flight_answers_after_the_board_forgets(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    """THE test. The entire point of the job.

    The board no longer carries this flight -- it has rolled out of the window,
    which is what the empty Board() stands for. The archived row answers
    anyway, with no network call, through the ordinary cache path that a
    customer's check already goes through.

    This is the four-year claim window working.
    """
    fold_in(
        session_factory,
        "iaa",
        [
            _flight(
                "BZ734",
                FlightStatus.CANCELLED,
                actual_departure=None,
            )
        ],
    )

    forgetful = Board([])
    provider = CachingProvider(forgetful, session_factory, ttl=timedelta(0))
    found = await provider.fetch("BZ734", WHEN)

    assert forgetful.calls == 0, "the board was asked for something we already had"
    assert len(found) == 1
    assert found[0].status is FlightStatus.CANCELLED
    assert found[0].destination_iata == "HER"
