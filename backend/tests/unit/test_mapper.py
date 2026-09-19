"""Tests for the RawFlight -> FlightFacts mapper.

The mapper is the join between the two halves of the system, and almost every
test here is about the same thing: a gap in OUR data must never be presented to
a customer as a fact about THEIR flight.
"""

from datetime import UTC, date, datetime

import pytest

from app.domain.models import FlightFacts, FlightStatus
from app.providers.base import RawFlight
from app.providers.fake import FakeFlightProvider
from app.providers.mapper import MappingFailure, to_flight_facts

AUG_14 = date(2026, 8, 14)


def raw(**overrides: object) -> RawFlight:
    """A complete, well-formed TLV->LHR record, 4 hours late."""
    base: dict[str, object] = {
        "flight_number": "BA165",
        "flight_date": AUG_14,
        "status": FlightStatus.LANDED,
        "provider": "test",
        "airline_iata": "BA",
        "origin_iata": "TLV",
        "destination_iata": "LHR",
        "scheduled_departure": datetime(2026, 8, 14, 2, 20, tzinfo=UTC),
        "actual_departure": datetime(2026, 8, 14, 6, 20, tzinfo=UTC),
        "scheduled_arrival": datetime(2026, 8, 14, 7, 20, tzinfo=UTC),
        "actual_arrival": datetime(2026, 8, 14, 11, 20, tzinfo=UTC),
    }
    base.update(overrides)
    return RawFlight(**base)  # type: ignore[arg-type]


# --- The happy path ----------------------------------------------------------


def test_a_complete_record_becomes_flight_facts() -> None:
    """Three codes in, a fully-described flight out."""
    facts = to_flight_facts(raw())
    assert isinstance(facts, FlightFacts)
    assert facts.origin_country == "IL"
    assert facts.destination_country == "GB"
    assert facts.airline_country == "GB"
    assert facts.arrival_delay_hours == 4.0


def test_distance_is_computed_from_our_own_reference_data() -> None:
    """Not taken from the provider, even when the provider offers one.

    AeroDataBox returns a greatCircleDistance field. We ignore it: distance
    decides which compensation band applies, so it must come from one source we
    control and can test, not vary with whichever provider answered.
    """
    facts = to_flight_facts(raw())
    assert isinstance(facts, FlightFacts)
    assert facts.distance_km == pytest.approx(3588.6, abs=1.0)


def test_timestamps_pass_through_untouched() -> None:
    """The mapper enriches; it does not adjust times."""
    record = raw()
    facts = to_flight_facts(record)
    assert isinstance(facts, FlightFacts)
    assert facts.actual_arrival == record.actual_arrival
    assert facts.scheduled_departure == record.scheduled_departure


def test_a_cancelled_record_maps_cleanly_without_actual_times() -> None:
    """Cancellations have no actual times and never will. That is not a gap in
    the data, so it must not be treated as one."""
    facts = to_flight_facts(
        raw(status=FlightStatus.CANCELLED, actual_departure=None, actual_arrival=None)
    )
    assert isinstance(facts, FlightFacts)
    assert facts.is_cancelled is True
    assert facts.has_complete_timing is True


def test_an_en_route_record_maps_without_an_arrival_time() -> None:
    """Also not a gap: the flight simply has not landed yet. The rules decide
    what that means."""
    facts = to_flight_facts(raw(status=FlightStatus.EN_ROUTE, actual_arrival=None))
    assert isinstance(facts, FlightFacts)
    assert facts.arrival_delay_hours is None


# --- Gaps in OUR data --------------------------------------------------------
#
# The theme of this file. Every case below would, if mishandled, tell a customer
# their flight does not qualify when the truth is that we could not look it up.


def test_an_unknown_airport_is_a_failure_not_a_verdict() -> None:
    """The single most important test in this module.

    ZZZ is not in airports.csv. Without a country we cannot say which law
    applies, and without coordinates we cannot say how much. Any answer other
    than "ask a person" would be invented.
    """
    result = to_flight_facts(raw(origin_iata="ZZZ"))
    assert isinstance(result, MappingFailure)
    assert "ZZZ" in result.reason
    assert "departure airport" in result.reason


def test_an_unknown_airline_is_a_failure() -> None:
    """We could guess that an unrecognised carrier is not European.

    That guess fails in exactly one direction: it turns "we have not heard of
    this airline" into "this airline is not European", which silently denies
    every EC261 and UK261 arrival claim it touches. There is no safe default,
    so there is no default.
    """
    result = to_flight_facts(raw(airline_iata="QQ"))
    assert isinstance(result, MappingFailure)
    assert "we do not recognise the airline QQ" in result.problems


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("origin_iata", "departure airport"),
        ("destination_iata", "arrival airport"),
        ("airline_iata", "which airline operated it"),
    ],
)
def test_a_missing_code_is_reported_by_name(field: str, expected: str) -> None:
    """Absent and unrecognised are different problems with different fixes, and
    the message says which one happened."""
    result = to_flight_facts(raw(**{field: None}))
    assert isinstance(result, MappingFailure)
    assert expected in result.reason


def test_no_scheduled_time_at_all_is_a_failure() -> None:
    """A scheduled time is the baseline every delay is measured against.

    With neither end there is no question to answer, only a guess to make.
    """
    result = to_flight_facts(raw(scheduled_departure=None, scheduled_arrival=None))
    assert isinstance(result, MappingFailure)
    assert "time" in result.reason


@pytest.mark.parametrize(
    ("missing", "measurable", "unmeasurable"),
    [
        ("scheduled_arrival", "departure_delay_hours", "arrival_delay_hours"),
        ("scheduled_departure", "arrival_delay_hours", "departure_delay_hours"),
    ],
)
def test_one_end_of_the_journey_is_enough_to_be_mapped(
    missing: str, measurable: str, unmeasurable: str
) -> None:
    """A source that knows one end is not a broken source.

    An airport board publishes the movement at its own airport: Ben Gurion
    records when a flight left Ben Gurion and never learns when it reached
    Heraklion. Rejecting that record would throw away an authoritative fact
    about a real flight -- and it is the fact the Israeli law measures.

    The half we do have stays measurable; the half we do not stays None, and
    the rule that needs it says NEEDS_REVIEW in its own words rather than
    having this layer refuse the flight on its behalf.
    """
    result = to_flight_facts(raw(**{missing: None}))

    assert not isinstance(result, MappingFailure), result
    assert getattr(result, measurable) is not None
    assert getattr(result, unmeasurable) is None


def test_every_problem_is_reported_at_once() -> None:
    """Not just the first.

    "We do not recognise ZZZ or QQ" is one round trip to fix. Three successive
    single-problem reports is three, and the third only appears after the first
    two are fixed.
    """
    result = to_flight_facts(
        raw(origin_iata="ZZZ", destination_iata="QQQ", airline_iata="XQ9")
    )
    assert isinstance(result, MappingFailure)
    assert len(result.problems) == 3
    for code in ("ZZZ", "QQQ", "XQ9"):
        assert code in result.reason


def test_the_failure_reads_as_a_sentence() -> None:
    """It is shown to a customer, not only written to a log."""
    result = to_flight_facts(raw(origin_iata="ZZZ", airline_iata="QQ"))
    assert isinstance(result, MappingFailure)
    assert result.reason.startswith("We could not fully identify flight BA165")
    assert result.reason.endswith("Someone will check this by hand.")
    assert "; and " in result.reason  # two problems joined readably


def test_the_original_record_is_kept_on_a_failure() -> None:
    """So the failure can be diagnosed, and so the raw payload can still be
    stored against the check."""
    result = to_flight_facts(raw(origin_iata="ZZZ"))
    assert isinstance(result, MappingFailure)
    assert result.raw.origin_iata == "ZZZ"
    assert result.raw.provider == "test"


# --- Corrupt records ---------------------------------------------------------


def test_arriving_before_departing_is_rejected() -> None:
    """A record that cannot be true, usually a date or timezone slip upstream.

    Left alone it yields a negative delay, which reads as a spectacularly early
    flight and produces a confident "no".
    """
    result = to_flight_facts(
        raw(
            actual_departure=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            actual_arrival=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        )
    )
    assert isinstance(result, MappingFailure)
    assert "actual arrival time is not after" in result.reason


def test_a_scheduled_arrival_before_its_departure_is_rejected() -> None:
    result = to_flight_facts(
        raw(
            scheduled_departure=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
            scheduled_arrival=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
        )
    )
    assert isinstance(result, MappingFailure)
    assert "scheduled arrival time is not after" in result.reason


def test_a_flight_that_returned_to_where_it_started_is_reviewed() -> None:
    """Rare but real: an aircraft that turned back and was logged as arrived.

    There is no journey to measure, and the compensation question becomes
    "where was the final destination", which needs a person.
    """
    result = to_flight_facts(raw(origin_iata="TLV", destination_iata="TLV"))
    assert isinstance(result, MappingFailure)
    assert "no journey to measure" in result.reason


# --- Wired to the real provider ----------------------------------------------


async def test_the_fake_providers_scenarios_map_as_intended() -> None:
    """End to end over the port: provider -> mapper, no rules involved.

    Guards the two layers agreeing with each other, which unit tests of either
    one alone cannot see.
    """
    provider = FakeFlightProvider()

    for number in ("BA165", "LY324", "LH687", "LY1"):
        for record in await provider.fetch(number, AUG_14):
            assert isinstance(to_flight_facts(record), FlightFacts), number

    # The scenario that exists precisely to fail here.
    unknown = (await provider.fetch("ZZ999", AUG_14))[0]
    assert isinstance(to_flight_facts(unknown), MappingFailure)


async def test_both_matches_of_a_double_flight_map(
) -> None:
    """FR1234 flew twice that day and both records must enrich independently."""
    provider = FakeFlightProvider()
    mapped = [to_flight_facts(r) for r in await provider.fetch("FR1234", AUG_14)]
    assert all(isinstance(m, FlightFacts) for m in mapped)
    assert mapped[0].arrival_delay_hours != mapped[1].arrival_delay_hours  # type: ignore[union-attr]
