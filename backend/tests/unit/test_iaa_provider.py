"""Reading the Ben Gurion board.

These tests are built from a recorded response (`fixtures/live_iaa_bz.json`),
captured from data.gov.il on 2026-09-19. It contains the flights that started
this work: BZ734 and BZ744, both cancelled, both absent from the commercial
feed the system was using.

What is being protected here is not "the parser parses". It is three specific
ways this feed will produce a confidently wrong answer if read naively, each of
which changes money:

  * a future flight whose "current time" equals its scheduled time is not an
    on-time flight, it is a flight that has not happened;
  * a zero-padded flight number is the same flight as the unpadded one;
  * a date outside the published window is unknown, not absent.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from app.domain.models import FlightStatus
from app.providers.base import ProviderCoverageGap, ProviderUnavailable
from app.providers.iaa import IsraelAirportsProvider

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "providers"
    / "fixtures"
    / "live_iaa_bz.json"
)


def _board(records: list[dict] | None = None) -> httpx.AsyncClient:
    """A client serving the recorded board, or a chosen subset of it."""
    payload = json.loads(FIXTURE.read_text())
    if records is not None:
        payload["result"]["records"] = records
        payload["result"]["total"] = len(records)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _records() -> list[dict]:
    return json.loads(FIXTURE.read_text())["result"]["records"]


async def _fetch(number: str, when: date, records: list[dict] | None = None):
    async with _board(records) as client:
        provider = IsraelAirportsProvider(client=client)
        return await provider.fetch(number, when)


# --- The flights that started this ------------------------------------------


async def test_a_cancelled_flight_the_commercial_feed_did_not_have() -> None:
    """BZ734 on 19 September. The whole reason this adapter exists.

    AeroDataBox returned 204 for this flight. The board has it, and has it as
    cancelled -- which is exactly the class of flight that is worth money and
    the class the other feed drops.
    """
    flights = await _fetch("BZ734", date(2026, 9, 19))

    assert len(flights) == 1
    flight = flights[0]
    assert flight.status is FlightStatus.CANCELLED
    assert flight.origin_iata == "TLV"
    assert flight.destination_iata == "HER"
    assert flight.airline_iata == "BZ"


async def test_the_departure_half_is_populated_and_the_arrival_half_is_not(
) -> None:
    """A departure row describes one end of the journey and says so.

    Ben Gurion knows when the aircraft left Ben Gurion. It does not know when it
    reached Heraklion, and inventing a landing time from the schedule would put
    a number into an EC261 calculation that nobody measured.
    """
    flights = await _fetch("BZ756", date(2026, 9, 19))
    flight = flights[0]

    assert flight.scheduled_departure is not None
    assert flight.scheduled_arrival is None
    assert flight.actual_arrival is None


# --- The three traps ---------------------------------------------------------


async def test_a_flight_that_has_not_departed_has_no_actual_time() -> None:
    """The trap that would have been silent.

    Every future flight on this board carries CHPTOL == CHSTOL, because
    "current time" for a flight that has not moved is its schedule. Reading that
    as an actual departure would manufacture a perfectly punctual record for a
    flight that has not happened -- and, worse, a punctual record for a flight
    that goes on to be delayed by six hours.

    BZ756 on the 19th is ON TIME, i.e. still upcoming.
    """
    flights = await _fetch("BZ756", date(2026, 9, 19))
    flight = flights[0]

    assert flight.status is FlightStatus.SCHEDULED
    assert flight.actual_departure is None, (
        "an estimate was read as an actual departure"
    )


async def test_a_departed_flight_does_get_its_actual_time() -> None:
    """The other side of the same rule: once settled, the time is a fact."""
    records = [
        {
            "CHOPER": "BZ",
            "CHFLTN": "734",
            "CHAORD": "D",
            "CHLOC1": "HER",
            "CHSTOL": "2026-09-19T08:00:00",
            "CHPTOL": "2026-09-19T11:30:00",
            "CHRMINE": "DEPARTED",
        }
    ]
    flights = await _fetch("BZ734", date(2026, 9, 19), records)
    flight = flights[0]

    assert flight.status is FlightStatus.EN_ROUTE
    assert flight.actual_departure is not None
    delay = flight.actual_departure - flight.scheduled_departure  # type: ignore[operator]
    assert delay.total_seconds() / 3600 == pytest.approx(3.5)


async def test_zero_padded_numbers_match_the_unpadded_request() -> None:
    """El Al 16 is stored as "016". A string comparison finds nothing.

    A customer typing LY16 would be told their flight does not exist.
    """
    records = [
        {
            "CHOPER": "LY",
            "CHFLTN": "016",
            "CHAORD": "A",
            "CHLOC1": "BOS",
            "CHSTOL": "2026-09-19T13:55:00",
            "CHPTOL": "2026-09-19T13:15:00",
            "CHRMINE": "LANDED",
        }
    ]
    flights = await _fetch("LY16", date(2026, 9, 19), records)

    assert len(flights) == 1
    assert flights[0].airline_iata == "LY"


async def test_an_arrival_fills_the_other_half() -> None:
    """Direction decides which end we know. An arrival knows the landing."""
    records = [
        {
            "CHOPER": "LY",
            "CHFLTN": "016",
            "CHAORD": "A",
            "CHLOC1": "BOS",
            "CHSTOL": "2026-09-19T13:55:00",
            "CHPTOL": "2026-09-19T13:15:00",
            "CHRMINE": "LANDED",
        }
    ]
    flight = (await _fetch("LY16", date(2026, 9, 19), records))[0]

    assert flight.origin_iata == "BOS"
    assert flight.destination_iata == "TLV"
    assert flight.actual_arrival is not None
    assert flight.scheduled_departure is None
    assert flight.actual_departure is None


async def test_a_date_outside_the_window_is_unknown_not_absent() -> None:
    """The board publishes a rolling few days. Older than that is not a "no".

    Returning empty here would tell somebody with a three-week-old cancelled
    flight -- a perfectly valid claim -- that their flight never existed.
    """
    with pytest.raises(ProviderCoverageGap) as caught:
        await _fetch("BZ734", date(2026, 3, 1))

    assert "outside" in str(caught.value)


async def test_a_flight_inside_the_window_that_is_simply_not_there_is_empty(
) -> None:
    """The opposite case, and it must stay an ordinary answer.

    Inside the published days the board is authoritative, so absence is real
    and the customer should be told to check the number.
    """
    flights = await _fetch("BZ999", date(2026, 9, 19))
    assert flights == ()


# --- Times -------------------------------------------------------------------


async def test_local_times_become_utc_across_the_dst_boundary() -> None:
    """Israel is +3 in September and +2 in December.

    A hardcoded offset is wrong for part of every year, and an hour of error is
    enough to move a flight across a compensation threshold.
    """
    summer = [
        {
            "CHOPER": "BZ",
            "CHFLTN": "734",
            "CHAORD": "D",
            "CHLOC1": "HER",
            "CHSTOL": "2026-09-19T08:00:00",
            "CHPTOL": "2026-09-19T08:00:00",
            "CHRMINE": "ON TIME",
        }
    ]
    winter = [
        {
            **summer[0],
            "CHSTOL": "2026-12-19T08:00:00",
            "CHPTOL": "2026-12-19T08:00:00",
        }
    ]

    s = (await _fetch("BZ734", date(2026, 9, 19), summer))[0]
    w = (await _fetch("BZ734", date(2026, 12, 19), winter))[0]

    assert s.scheduled_departure == datetime(2026, 9, 19, 5, 0, tzinfo=UTC)
    assert w.scheduled_departure == datetime(2026, 12, 19, 6, 0, tzinfo=UTC)


async def test_every_time_is_timezone_aware() -> None:
    """RawFlight refuses naive datetimes; this proves the edge converts."""
    flight = (await _fetch("BZ734", date(2026, 9, 19)))[0]
    assert flight.scheduled_departure is not None
    assert flight.scheduled_departure.tzinfo is not None


# --- Failure -----------------------------------------------------------------


async def test_an_unreachable_dataset_raises_rather_than_returning_empty(
) -> None:
    """"data.gov.il is down" must never read as "your flight does not exist"."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        provider = IsraelAirportsProvider(client=c)
        with pytest.raises(ProviderUnavailable):
            await provider.fetch("BZ734", date(2026, 9, 19))


async def test_an_unparsable_flight_number_is_not_an_error() -> None:
    """Junk in the box is a question we can answer: there is no such flight."""
    flights = await _fetch("???", date(2026, 9, 19))
    assert flights == ()


# --- Flight numbers as passengers actually hold them -------------------------


async def test_a_relief_section_suffix_is_not_a_different_flight() -> None:
    """LY385A is the second section of LY385, and the board files both under
    the bare number.

    Airlines add a trailing letter when a service is oversubscribed and a
    relief aircraft is put on. The passenger's boarding pass says LY385A;
    refusing the suffix told them their flight does not exist.
    """
    records = [
        {
            "CHOPER": "LY",
            "CHFLTN": "385",
            "CHAORD": "D",
            "CHLOC1": "FCO",
            "CHSTOL": "2026-09-19T08:00:00",
            "CHPTOL": "2026-09-19T08:00:00",
            "CHRMINE": "ON TIME",
        }
    ]
    flights = await _fetch("LY385A", date(2026, 9, 19), records)

    assert len(flights) == 1
    assert flights[0].airline_iata == "LY"


async def test_a_two_character_number_is_still_refused() -> None:
    """The suffix rule must not turn junk into a lookup.

    "X1" is an airline code and one digit stripped to nothing; it is not a
    flight number, and asking the board about it is wasted.
    """
    assert await _fetch("X1", date(2026, 9, 19), []) == ()
