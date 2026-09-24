

# --- records that describe the same flight -----------------------------------
#
# Observed live. IZ164 on 23 September offered two options reading
# "LCA → TLV, departing 04:30 UTC" and "LCA → TLV, departing 04:30 UTC", and
# clicking either did nothing: both produced the same key, so the filter kept
# both, the check was still ambiguous, and the same screen came back.
#
# The underlying mistake was treating "two records" as "two flights".
# Ambiguity means two DIFFERENT flights share a number, which a passenger can
# answer. Two records of one flight is a question nobody can answer.


def _same_flight(status, *, scheduled=None):  # type: ignore[no-untyped-def]
    from datetime import UTC, date, datetime

    from app.domain.models import FlightStatus
    from app.providers.base import RawFlight

    return RawFlight(
        flight_number="IZ164",
        flight_date=date(2026, 9, 23),
        status=status if isinstance(status, FlightStatus) else FlightStatus[status],
        provider="iaa",
        airline_iata="IZ",
        origin_iata="LCA",
        destination_iata="TLV",
        scheduled_departure=scheduled,
        scheduled_arrival=None,
        actual_departure=None,
        actual_arrival=None,
        raw={},
    )


def test_two_records_of_one_flight_are_not_a_choice() -> None:
    """Identical options with identical keys are a dead end, not a question."""
    from datetime import UTC, datetime

    from app.domain.models import FlightStatus
    from app.services.eligibility import _collapse_duplicates

    when = datetime(2026, 9, 23, 4, 30, tzinfo=UTC)
    kept, conflicted = _collapse_duplicates(
        [_same_flight(FlightStatus.LANDED, scheduled=when)] * 2
    )

    assert len(kept) == 1
    assert conflicted is False


def test_the_record_that_knows_more_is_the_one_kept() -> None:
    """A row with a scheduled time can be reasoned about; one without mostly
    cannot."""
    from datetime import UTC, datetime

    from app.domain.models import FlightStatus
    from app.services.eligibility import _collapse_duplicates

    when = datetime(2026, 9, 23, 4, 30, tzinfo=UTC)
    thin = _same_flight(FlightStatus.LANDED)
    full = _same_flight(FlightStatus.LANDED, scheduled=when)

    # Same route, so they collapse -- but only one of them says when.
    kept, _ = _collapse_duplicates([thin])
    assert kept[0].scheduled_departure is None

    kept, _ = _collapse_duplicates([full, full])
    assert kept[0].scheduled_departure == when


def test_sources_disagreeing_about_the_flight_is_flagged() -> None:
    """THE case that matters.

    One row says it landed, another says it was cancelled. A wrong
    "cancelled" promises money that is not owed; a wrong "landed" denies
    money that is. Both are expensive, so neither is guessed at.
    """
    from app.domain.models import FlightStatus
    from app.services.eligibility import _collapse_duplicates

    kept, conflicted = _collapse_duplicates(
        [
            _same_flight(FlightStatus.LANDED),
            _same_flight(FlightStatus.CANCELLED),
        ]
    )

    assert len(kept) == 1, "still one flight"
    assert conflicted is True, "and somebody has to look at it"


def test_genuinely_different_flights_are_still_a_choice() -> None:
    """Collapsing must not swallow a real ambiguity.

    Two services really do share a number some days, and that is a question
    the passenger can answer -- they know which one they were on.
    """
    from datetime import UTC, datetime

    from app.domain.models import FlightStatus
    from app.services.eligibility import _collapse_duplicates

    morning = _same_flight(FlightStatus.LANDED, scheduled=datetime(2026, 9, 23, 4, 30, tzinfo=UTC))
    evening = _same_flight(FlightStatus.LANDED, scheduled=datetime(2026, 9, 23, 19, 5, tzinfo=UTC))

    kept, conflicted = _collapse_duplicates([morning, evening])

    assert len(kept) == 2
    assert conflicted is False
