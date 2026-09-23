"""Tests for the public board of recently disrupted flights.

WHAT THIS ENDPOINT IS, AND WHY IT IS TESTED THIS WAY
----------------------------------------------------
It is the one part of the landing page that is evidence rather than argument:
real cancellations from the archive, priced. The risk is therefore not that it
looks wrong but that it says something untrue -- a figure where the data
cannot support one, or a row for a flight that was fine.

So these test what it CLAIMS, not how it is arranged.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.models import FlightLookup
from app.db.session import create_session_factory
from app.providers.cache import encode
from app.providers.base import RawFlight
from app.domain.models import FlightStatus


def _store(engine, flights, provider="iaa", day=None):  # type: ignore[no-untyped-def]
    """Put flights into the archive the way the cron would."""
    day = day or datetime.now(UTC).date()
    factory = create_session_factory(engine)
    with factory() as session:
        for flight in flights:
            session.add(
                FlightLookup(
                    provider=provider,
                    flight_number=flight.flight_number,
                    flight_date=day,
                    observed_at=datetime.now(UTC),
                    is_final=True,
                    flights=[encode(flight)],
                )
            )
        session.commit()


def _flight(number, status, *, origin="TLV", destination="HER", delay_h=0.0, day=None):  # type: ignore[no-untyped-def]
    day = day or datetime.now(UTC).date()
    scheduled = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8)
    actual = scheduled + timedelta(hours=delay_h) if delay_h else None
    return RawFlight(
        flight_number=number,
        flight_date=day,
        status=status,
        provider="iaa",
        airline_iata=number[:2],
        origin_iata=origin,
        destination_iata=destination,
        scheduled_departure=scheduled,
        scheduled_arrival=None,
        actual_departure=actual,
        actual_arrival=None,
        raw={},
    )


def test_an_empty_archive_is_an_empty_board(client: TestClient) -> None:
    """Not an error, and not a fabricated row.

    A quiet couple of days at Ben Gurion is a real answer. The temptation
    here is to show something rather than nothing, and something invented is
    exactly what the disclaimer on a competitor's board is admitting to.
    """
    response = client.get("/api/v1/disruptions")

    assert response.status_code == 200
    assert response.json()["rows"] == []


def test_a_cancellation_is_listed_and_priced(client: TestClient) -> None:
    """The row that pays. TLV -> HER is 971 km, the first band."""
    _store(client.app.state.engine, [_flight("BZ734", FlightStatus.CANCELLED)])

    rows = client.get("/api/v1/disruptions").json()["rows"]

    assert len(rows) == 1
    row = rows[0]
    assert row["flight_number"] == "BZ734"
    assert row["status"] == "CANCELLED"
    assert row["airline"] == "BZ"
    assert row["origin"] == "TLV" and row["destination"] == "HER"
    assert "1,530" in (row["amount"] or ""), row


def test_an_on_time_flight_is_not_on_the_board(client: TestClient) -> None:
    """The board is a list of things that went wrong.

    A punctual flight appearing here would be a row that can only mislead --
    somebody looking for their own flight would find it and assume a claim.
    """
    _store(client.app.state.engine, [_flight("LY315", FlightStatus.LANDED)])

    assert client.get("/api/v1/disruptions").json()["rows"] == []


def test_a_short_delay_is_not_on_the_board(client: TestClient) -> None:
    """Nothing under three hours is payable under any of the three regimes,
    so a shorter delay here is a row that can only disappoint."""
    _store(client.app.state.engine, [_flight("LY315", FlightStatus.LANDED, delay_h=1.5)])

    assert client.get("/api/v1/disruptions").json()["rows"] == []


def test_a_long_delay_is_listed(client: TestClient) -> None:
    _store(client.app.state.engine, [_flight("LY315", FlightStatus.LANDED, delay_h=5.0)])

    rows = client.get("/api/v1/disruptions").json()["rows"]

    assert len(rows) == 1
    assert rows[0]["status"] == "DELAYED"
    assert rows[0]["delay_hours"] == 5.0


def test_a_realistic_day_shows_both_cancellations_and_delays(
    client: TestClient,
) -> None:
    """THE reason this board sorts by date rather than by severity.

    `find` ranks worst-first, which is right for a report somebody reads to
    decide what to chase. Ranked that way a board shows nothing but
    cancellations -- every delay falls off the end -- and reads as though
    flights are only ever cancelled and never merely late.

    The proportions here are a measured day at Ben Gurion: 22 September 2026
    had 12 cancellations against 79 delays of an hour or more.

    Note what this does NOT claim. On a day with sixty cancellations -- a
    strike, a closure -- they fill the board and the delays do fall off. That
    is correct: on such a day the cancellations ARE the story, and a board
    that hid some of them to make room for a late flight would be worse.
    """
    _store(
        client.app.state.engine,
        [_flight(f"BZ{700 + i}", FlightStatus.CANCELLED) for i in range(12)]
        + [_flight(f"LY{300 + i}", FlightStatus.LANDED, delay_h=4.0) for i in range(20)],
    )

    rows = client.get("/api/v1/disruptions").json()["rows"]
    kinds = {r["status"] for r in rows}

    assert kinds == {"CANCELLED", "DELAYED"}, kinds


def test_the_worse_event_leads_within_a_day(client: TestClient) -> None:
    """Chronological between days, severity within one."""
    _store(
        client.app.state.engine,
        [
            _flight("LY315", FlightStatus.LANDED, delay_h=6.0),
            _flight("BZ734", FlightStatus.CANCELLED),
        ],
    )

    rows = client.get("/api/v1/disruptions").json()["rows"]

    assert [r["flight_number"] for r in rows] == ["BZ734", "LY315"]


def test_the_window_is_bounded(client: TestClient) -> None:
    """A landing page must not be able to ask for the whole archive.

    Unbounded, one crafted query walks every row we hold and runs the rules
    over each -- which is a free denial of service on the public endpoint.
    """
    assert client.get("/api/v1/disruptions?days=999").status_code == 422
    assert client.get("/api/v1/disruptions?days=0").status_code == 422
    assert client.get("/api/v1/disruptions?days=14").status_code == 200


def test_an_older_flight_falls_outside_the_default_window(client: TestClient) -> None:
    """"Recently" means the last day or two to somebody whose flight was
    yesterday."""
    old = datetime.now(UTC).date() - timedelta(days=9)
    _store(client.app.state.engine, [_flight("BZ734", FlightStatus.CANCELLED, day=old)], day=old)

    assert client.get("/api/v1/disruptions").json()["rows"] == []
    assert client.get("/api/v1/disruptions?days=14").json()["rows"] != []
