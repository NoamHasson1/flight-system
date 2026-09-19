"""Tests for the AeroDataBox adapter.

No network. httpx ships a MockTransport, so the real client code runs end to
end -- headers, status-code handling, retries, JSON parsing -- against scripted
responses. That is strictly better than patching: the thing under test is the
actual request pipeline, not a stand-in for it.

The fixtures are MODELLED from the published schema rather than recorded,
because no API key existed when this was written. See fixtures/aerodatabox/
README.md. Any drift from the real API surfaces here as a failing parse test.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.domain.models import FlightStatus
from app.providers.aerodatabox import AeroDataBoxProvider, _parse_time, _status
from app.providers.base import (
    FlightDataProvider,
    ProviderAuthError,
    ProviderRateLimited,
    ProviderResponseInvalid,
    ProviderUnavailable,
)
from app.providers.registry import AVAILABLE, build_provider

FIXTURES = Path(__file__).resolve().parents[2] / "app/providers/fixtures/aerodatabox"
AUG_14 = date(2026, 8, 14)


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def provider_returning(
    *responses: httpx.Response, max_attempts: int = 3
) -> tuple[AeroDataBoxProvider, list[httpx.Request]]:
    """An adapter wired to scripted HTTP responses, plus the requests it made.

    The last response repeats if the client asks more times than we scripted.
    """
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return (
        AeroDataBoxProvider(
            "test-key", client=client, max_attempts=max_attempts,
            backoff_seconds=0.0,
        ),
        seen,
    )


def ok(payload: Any) -> httpx.Response:
    return httpx.Response(200, json=payload)


# --- The contract ------------------------------------------------------------


def test_the_adapter_satisfies_the_provider_protocol() -> None:
    """The same assertion made against the fake.

    Both adapters satisfy one contract, which is what lets everything above this
    layer be tested against the fake and run against the real thing.
    """
    adapter, _ = provider_returning(ok([]))
    assert isinstance(adapter, FlightDataProvider)
    assert adapter.name == "aerodatabox"


# --- Parsing the real schema -------------------------------------------------


async def test_a_delayed_arrival_is_parsed() -> None:
    """The normal path, against the documented schema."""
    adapter, _ = provider_returning(ok(fixture("arrived_delayed")))
    flights = await adapter.fetch("BA165", AUG_14)

    assert len(flights) == 1
    flight = flights[0]
    assert flight.airline_iata == "BA"
    assert flight.origin_iata == "TLV"
    assert flight.destination_iata == "LHR"
    assert flight.status is FlightStatus.LANDED
    assert flight.scheduled_arrival == datetime(2026, 8, 14, 7, 20, tzinfo=UTC)
    assert flight.actual_arrival == datetime(2026, 8, 14, 11, 20, tzinfo=UTC)


async def test_runway_time_is_preferred_over_revised_time() -> None:
    """runwayTime is a fact; revisedTime is an estimate.

    In the fixture the arrival was revised to 11:15 and actually touched down at
    11:20. Taking the estimate would understate the delay by five minutes --
    which, three hours from the threshold, is exactly the sort of error that
    decides a claim.
    """
    adapter, _ = provider_returning(ok(fixture("arrived_delayed")))
    flight = (await adapter.fetch("BA165", AUG_14))[0]
    assert flight.actual_arrival == datetime(2026, 8, 14, 11, 20, tzinfo=UTC)
    assert flight.actual_departure == datetime(2026, 8, 14, 6, 20, tzinfo=UTC)


async def test_revised_time_is_used_when_there_is_no_runway_time() -> None:
    """An estimate beats nothing. Inventing a time from the schedule would turn
    a missing measurement into a confident zero delay."""
    payload = fixture("arrived_delayed")
    del payload[0]["arrival"]["runwayTime"]
    adapter, _ = provider_returning(ok(payload))
    flight = (await adapter.fetch("BA165", AUG_14))[0]
    assert flight.actual_arrival == datetime(2026, 8, 14, 11, 15, tzinfo=UTC)


async def test_a_cancelled_flight_has_no_actual_times() -> None:
    """Note the American spelling in the vendor's vocabulary: "Canceled"."""
    adapter, _ = provider_returning(ok(fixture("cancelled")))
    flight = (await adapter.fetch("LH687", AUG_14))[0]
    assert flight.status is FlightStatus.CANCELLED
    assert flight.actual_departure is None
    assert flight.actual_arrival is None
    assert flight.scheduled_departure is not None


async def test_two_matches_are_both_returned() -> None:
    """The real reason `fetch` returns a sequence.

    This fixture also omits aircraft, terminal and quality entirely, so it
    doubles as proof the parser tolerates absent optional fields.
    """
    adapter, _ = provider_returning(ok(fixture("two_matches")))
    flights = await adapter.fetch("FR1234", AUG_14)
    assert len(flights) == 2
    delays = [
        (f.actual_arrival - f.scheduled_arrival).total_seconds() / 3600
        for f in flights
        if f.actual_arrival and f.scheduled_arrival
    ]
    assert delays[0] < 0.2 and delays[1] > 4.0


async def test_the_untouched_payload_is_preserved() -> None:
    """Kept so a decision can be re-explained, or re-run against corrected
    rules, without paying the provider again."""
    adapter, _ = provider_returning(ok(fixture("arrived_delayed")))
    flight = (await adapter.fetch("BA165", AUG_14))[0]
    assert flight.raw["callSign"] == "BAW165"
    assert flight.raw["aircraft"]["model"] == "Boeing 787-9"


# --- The timestamp format ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-08-14 02:20Z", datetime(2026, 8, 14, 2, 20, tzinfo=UTC)),
        ("2026-08-14 02:20:35Z", datetime(2026, 8, 14, 2, 20, 35, tzinfo=UTC)),
        ("2026-08-14T02:20Z", datetime(2026, 8, 14, 2, 20, tzinfo=UTC)),
        ("2026-08-14 02:20", datetime(2026, 8, 14, 2, 20, tzinfo=UTC)),
    ],
)
def test_the_vendors_timestamp_format_is_parsed(
    text: str, expected: datetime
) -> None:
    """AeroDataBox timestamps are NOT ISO 8601.

    They put a space where the T belongs, so `datetime.fromisoformat` rejects
    them outright. Seconds are sometimes present and sometimes not. The last
    case has no offset at all, which this vendor's `utc` field occasionally
    does -- treating that as local time would be worse than assuming UTC.
    """
    assert _parse_time(text) == expected


def test_a_local_timestamp_keeps_its_offset() -> None:
    """05:20+03:00 is 02:20 UTC, and must not be read as 05:20 UTC."""
    parsed = _parse_time("2026-08-14 05:20+03:00")
    assert parsed is not None
    assert parsed.astimezone(UTC) == datetime(2026, 8, 14, 2, 20, tzinfo=UTC)


@pytest.mark.parametrize("value", [None, "", "  ", "not a time", 12345, {}])
def test_unparseable_timestamps_become_none_not_an_exception(value: Any) -> None:
    """One bad timestamp must not take out the whole response.

    None travels downstream and becomes NEEDS_REVIEW, which is the correct
    outcome. Raising here would turn a partially-usable answer into no answer.
    """
    assert _parse_time(value) is None


# --- Status vocabulary -------------------------------------------------------


@pytest.mark.parametrize(
    ("vendor", "expected"),
    [
        ("Arrived", FlightStatus.LANDED),
        ("EnRoute", FlightStatus.EN_ROUTE),
        ("Departed", FlightStatus.EN_ROUTE),
        ("Approaching", FlightStatus.EN_ROUTE),
        ("Expected", FlightStatus.SCHEDULED),
        ("Boarding", FlightStatus.SCHEDULED),
        ("Delayed", FlightStatus.SCHEDULED),
        ("Canceled", FlightStatus.CANCELLED),
        ("Diverted", FlightStatus.DIVERTED),
        ("arrived", FlightStatus.LANDED),
        ("EN ROUTE", FlightStatus.EN_ROUTE),
    ],
)
def test_status_vocabulary_is_mapped(vendor: str, expected: FlightStatus) -> None:
    assert _status(vendor) is expected


def test_canceled_uncertain_becomes_unknown_not_cancelled() -> None:
    """The vendor thinks it was cancelled but will not commit. Neither do we.

    Mapping it to CANCELLED would put a maybe-cancellation through the
    cancellation path; UNKNOWN sends it to a person, which is what an uncertain
    fact deserves.
    """
    assert _status("CanceledUncertain") is FlightStatus.UNKNOWN


@pytest.mark.parametrize("value", ["SomethingNew", "", None, 42])
def test_unrecognised_statuses_become_unknown(value: Any) -> None:
    """If the vendor adds a status we have never seen, the right response is to
    ask a human -- not to guess which bucket it belongs in."""
    assert _status(value) is FlightStatus.UNKNOWN


# --- HTTP failures -----------------------------------------------------------


async def test_no_such_flight_returns_empty_rather_than_raising() -> None:
    """204 and 404 both mean "we looked and it is not there"."""
    for status in (204, 404):
        adapter, _ = provider_returning(httpx.Response(status))
        assert await adapter.fetch("XX999", AUG_14) == ()


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, ProviderAuthError), (403, ProviderAuthError), (429, ProviderRateLimited)],
)
async def test_client_errors_are_classified(
    status: int, expected: type[Exception]
) -> None:
    adapter, _ = provider_returning(httpx.Response(status))
    with pytest.raises(expected):
        await adapter.fetch("BA165", AUG_14)


async def test_a_401_explains_the_rapidapi_subscription_trap() -> None:
    """The commonest way this integration fails.

    A RapidAPI key can be perfectly valid while the account is not subscribed to
    this particular API, and the 401 that results looks identical to a wrong
    key. Saying so in the message saves an hour.
    """
    adapter, _ = provider_returning(httpx.Response(401))
    with pytest.raises(ProviderAuthError, match="not subscribed"):
        await adapter.fetch("BA165", AUG_14)


async def test_client_errors_are_not_retried() -> None:
    """Asking again with the same bad key just spends quota."""
    adapter, seen = provider_returning(httpx.Response(401))
    with pytest.raises(ProviderAuthError):
        await adapter.fetch("BA165", AUG_14)
    assert len(seen) == 1


async def test_server_errors_are_retried_then_give_up() -> None:
    """A 5xx might be transient, so it is worth asking again -- but only a
    bounded number of times, and then the failure must surface."""
    adapter, seen = provider_returning(httpx.Response(503), max_attempts=3)
    with pytest.raises(ProviderUnavailable):
        await adapter.fetch("BA165", AUG_14)
    assert len(seen) == 3


async def test_a_retry_that_succeeds_returns_the_result() -> None:
    """The point of retrying at all: one blip must not fail the request."""
    adapter, seen = provider_returning(
        httpx.Response(503), ok(fixture("arrived_delayed"))
    )
    flights = await adapter.fetch("BA165", AUG_14)
    assert len(flights) == 1
    assert len(seen) == 2


async def test_timeouts_are_retried_and_then_reported_as_unavailable() -> None:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectTimeout("too slow", request=request)

    adapter = AeroDataBoxProvider(
        "k", client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        max_attempts=2, backoff_seconds=0.0,
    )
    with pytest.raises(ProviderUnavailable):
        await adapter.fetch("BA165", AUG_14)
    assert attempts == 2


async def test_a_non_json_body_is_reported_as_an_invalid_response() -> None:
    """Loud on purpose: silently coercing an unrecognised payload is how wrong
    verdicts get shipped."""
    adapter, _ = provider_returning(httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(ProviderResponseInvalid):
        await adapter.fetch("BA165", AUG_14)


async def test_a_json_object_where_a_list_was_expected_is_invalid() -> None:
    """A signal that the vendor changed their schema."""
    adapter, _ = provider_returning(ok({"message": "something else"}))
    with pytest.raises(ProviderResponseInvalid, match="expected a list"):
        await adapter.fetch("BA165", AUG_14)


# --- The request itself ------------------------------------------------------


async def test_the_request_is_addressed_and_authenticated_correctly() -> None:
    adapter, seen = provider_returning(ok([]))
    await adapter.fetch("ba165", AUG_14)

    request = seen[0]
    assert request.url.path == "/flights/number/BA165/2026-08-14"
    assert request.headers["X-RapidAPI-Key"] == "test-key"
    assert request.headers["X-RapidAPI-Host"] == "aerodatabox.p.rapidapi.com"


async def test_optional_payload_is_switched_off() -> None:
    """Aircraft images and live positions are bytes we pay to transfer and then
    throw away. Compensation needs times, airports and status."""
    adapter, seen = provider_returning(ok([]))
    await adapter.fetch("BA165", AUG_14)
    assert seen[0].url.params["withAircraftImage"] == "false"
    assert seen[0].url.params["withLocation"] == "false"


def test_a_missing_api_key_fails_at_construction() -> None:
    """Not at request time.

    A missing key is a configuration mistake. Naming it when the application
    starts is far cheaper to diagnose than a 401 on a customer's first check.
    """
    for key in ("", "   "):
        with pytest.raises(ProviderAuthError, match="no API key configured"):
            AeroDataBoxProvider(key)


# --- The registry ------------------------------------------------------------


def test_the_registry_lists_every_provider() -> None:
    """Sorted, so adding one is a one-line diff rather than a reshuffle."""
    assert AVAILABLE == ("aerodatabox", "fake", "iaa")


def test_the_registry_builds_the_fake_without_a_key() -> None:
    """Which is what lets the whole system run before a subscription exists."""
    assert build_provider("fake").name == "fake"


def test_the_registry_builds_aerodatabox_with_a_key() -> None:
    assert build_provider("aerodatabox", api_key="k").name == "aerodatabox"


def test_an_unknown_provider_name_raises_value_error_not_a_provider_error() -> None:
    """A misconfigured provider name is a deployment mistake that should stop
    the application at startup -- not degrade into failed lookups that get
    reported to customers as NEEDS_REVIEW."""
    with pytest.raises(ValueError, match="unknown flight data provider"):
        build_provider("flightaware")


# --- Against a genuinely recorded response -----------------------------------


async def test_a_real_recorded_response_parses() -> None:
    """The fixture that is NOT modelled.

    Every other fixture in this suite was written by hand from AeroDataBox's
    published schema, because no subscription existed when the adapter was
    built. This one is a real response, recorded with
    scripts/record_fixtures.py once a key was available: El Al 315, Tel Aviv to
    Heathrow, 14 September 2026.

    It is the test that closes the gap between "the adapter handles their
    documentation" and "the adapter handles their API". If AeroDataBox changes
    the shape, this fails here rather than in front of a customer.
    """
    adapter, _ = provider_returning(ok(fixture("live_ly315")))
    flights = await adapter.fetch("LY315", date(2026, 9, 14))

    assert len(flights) == 1
    flight = flights[0]

    assert flight.airline_iata == "LY"
    assert flight.origin_iata == "TLV"
    assert flight.destination_iata == "LHR"
    assert flight.status is FlightStatus.LANDED

    # Their timestamps are "2026-09-14 07:10Z" -- a space where ISO 8601 puts a
    # T, which datetime.fromisoformat rejects outright.
    assert flight.scheduled_departure == datetime(2026, 9, 14, 7, 10, tzinfo=UTC)
    assert flight.scheduled_arrival == datetime(2026, 9, 14, 12, 35, tzinfo=UTC)

    # runwayTime preferred over revisedTime: 13:55 touchdown, not the 13:55
    # estimate -- and on departure the two genuinely differ (09:13 vs 09:12).
    assert flight.actual_departure == datetime(2026, 9, 14, 9, 13, tzinfo=UTC)
    assert flight.actual_arrival == datetime(2026, 9, 14, 13, 55, tzinfo=UTC)


async def test_the_real_response_survives_the_mapper() -> None:
    """Parsing it is not enough -- it has to enrich too.

    A live payload can parse perfectly and still fail the mapper: an airport or
    airline we do not carry in the reference data, an origin equal to a
    destination, timestamps that contradict each other. This runs the whole
    adapter-to-facts path on real data.
    """
    from app.providers.mapper import to_flight_facts
    from app.domain.models import FlightFacts

    adapter, _ = provider_returning(ok(fixture("live_ly315")))
    record = (await adapter.fetch("LY315", date(2026, 9, 14)))[0]
    facts = to_flight_facts(record)

    assert isinstance(facts, FlightFacts), getattr(facts, "reason", "")
    assert facts.origin_country == "IL"
    assert facts.destination_country == "GB"
    assert facts.airline_country == "IL"
    # Departed 2h 03m late, arrived 1h 20m late: the crew made up time. This is
    # the first real flight the system saw, and it is the exact case the rules
    # tests were built around.
    assert facts.departure_delay_hours == pytest.approx(2.05, abs=0.01)
    assert facts.arrival_delay_hours == pytest.approx(1.33, abs=0.01)


# --- Two different things arrive as 429 --------------------------------------


_THROTTLED = httpx.Response(
    429,
    json={
        "message": "You have exceeded the rate limit per second for your "
        "plan, PRO, by the API provider"
    },
)
_OUT_OF_QUOTA = httpx.Response(
    429, json={"message": "You have exceeded the MONTHLY quota for Requests"}
)


async def test_a_per_second_throttle_is_retried() -> None:
    """The normal shape of a good day here.

    Several passengers off one cancelled flight check it within the same
    second. RapidAPI answers 429 "rate limit per second", which clears almost
    immediately -- so refusing outright would turn a busy minute into a
    screenful of "we could not check your flight" for people who are owed
    money.
    """
    provider, seen = provider_returning(
        _THROTTLED, httpx.Response(200, json=fixture("arrived_delayed"))
    )
    flights = await provider.fetch("BA165", AUG_14)

    assert len(seen) == 2, "a temporary throttle was treated as permanent"
    assert len(flights) == 1


async def test_an_exhausted_monthly_quota_is_not_retried() -> None:
    """The other 429. Retrying spends what little is left and still fails; it
    is a billing problem and has to read as one."""
    provider, seen = provider_returning(_OUT_OF_QUOTA)

    with pytest.raises(ProviderRateLimited, match="quota exhausted"):
        await provider.fetch("BA165", AUG_14)

    assert len(seen) == 1, "quota exhaustion must not be retried"


async def test_unrelenting_throttling_still_reads_as_throttling() -> None:
    """Not as an outage: the fix is to slow down or raise the plan, and
    "unavailable" sends whoever reads it looking at the wrong thing."""
    provider, seen = provider_returning(_THROTTLED)

    with pytest.raises(ProviderRateLimited, match="throttled"):
        await provider.fetch("BA165", AUG_14)

    assert len(seen) == 3, "the retries were skipped"


# --- An estimate is not a measurement ----------------------------------------


def _movement(sched: str, revised: str | None = None, runway: str | None = None):
    block: dict = {
        "airport": {"iata": "TLV"},
        "scheduledTime": {"utc": sched},
    }
    if revised:
        block["revisedTime"] = {"utc": revised}
    if runway:
        block["runwayTime"] = {"utc": runway}
    return block


def _record(status: str, **movements):  # type: ignore[no-untyped-def]
    item = {"number": "BZ 736", "status": status, "airline": {"iata": "BZ"}}
    item.update(movements)
    return item


async def test_a_revised_time_on_a_future_flight_is_not_a_departure() -> None:
    """The trap this feed sets, and it is silent.

    On an undisrupted flight revisedTime equals scheduledTime exactly. Read
    unconditionally, every flight in next week's timetable reports as having
    departed precisely on time -- and a flight currently running three hours
    late reports as on time right up until it actually moves.
    """
    dep = _movement("2026-09-20 02:25Z", revised="2026-09-20 02:25Z")
    arr = _movement("2026-09-20 05:00Z", revised="2026-09-20 05:00Z")
    arr["airport"] = {"iata": "HER"}

    provider, _ = provider_returning(
        httpx.Response(200, json=[_record("Scheduled", departure=dep, arrival=arr)])
    )
    flight = (await provider.fetch("BZ736", AUG_14))[0]

    assert flight.status is FlightStatus.SCHEDULED
    assert flight.actual_departure is None, "an estimate was read as a departure"
    assert flight.actual_arrival is None


async def test_a_revised_time_counts_once_the_flight_has_moved() -> None:
    """The other half of the rule: after departure it is a measurement."""
    dep = _movement("2026-09-20 02:25Z", revised="2026-09-20 05:25Z")
    arr = _movement("2026-09-20 05:00Z", revised="2026-09-20 08:00Z")
    arr["airport"] = {"iata": "HER"}

    provider, _ = provider_returning(
        httpx.Response(200, json=[_record("Arrived", departure=dep, arrival=arr)])
    )
    flight = (await provider.fetch("BZ736", AUG_14))[0]

    assert flight.actual_departure is not None
    assert flight.actual_arrival is not None


async def test_an_airborne_flight_has_departed_but_not_arrived() -> None:
    """Its take-off is measured; its landing is still a forecast."""
    dep = _movement("2026-09-20 02:25Z", revised="2026-09-20 05:25Z")
    arr = _movement("2026-09-20 05:00Z", revised="2026-09-20 08:00Z")
    arr["airport"] = {"iata": "HER"}

    provider, _ = provider_returning(
        httpx.Response(200, json=[_record("EnRoute", departure=dep, arrival=arr)])
    )
    flight = (await provider.fetch("BZ736", AUG_14))[0]

    assert flight.actual_departure is not None
    assert flight.actual_arrival is None, "a predicted landing was read as real"


async def test_a_runway_time_is_always_a_fact() -> None:
    """Wheels up and wheels down are measurements whatever the status says."""
    dep = _movement("2026-09-20 02:25Z", runway="2026-09-20 05:26Z")
    arr = _movement("2026-09-20 05:00Z")
    arr["airport"] = {"iata": "HER"}

    provider, _ = provider_returning(
        httpx.Response(200, json=[_record("Unknown", departure=dep, arrival=arr)])
    )
    flight = (await provider.fetch("BZ736", AUG_14))[0]

    assert flight.actual_departure is not None
