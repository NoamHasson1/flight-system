"""The use case: "am I owed anything for this flight?"

One function, `check`, which orchestrates the three layers that already exist --
provider, mapper, rules -- and turns every way they can fail into an answer a
person can act on.

Nothing here makes a legal judgement; that all happened in `domain/rules`. What
this module owns is the shape of the conversation:

    "no such flight"        -> check the number and the date
    "which one was yours?"  -> two flights carried that number that day
    "we could not tell"     -> and here is what we could not tell
    a verdict               -> with the reasoning behind it

The HTTP layer (step 17) turns a CheckResult into a response; the database layer
(step 13) stores it. Both stay thin because the decision has already been made
by the time they see it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from app.domain.models import FlightFacts, Verdict
from app.observability import flow
from app.domain.rules import engine
from app.domain.rules.engine import EligibilityResult
from app.providers.base import (
    FlightDataError,
    FlightDataProvider,
    ProviderAuthError,
    ProviderRateLimited,
    RawFlight,
)
from app.providers.mapper import MappingFailure, to_flight_facts


class CheckStatus(StrEnum):
    """What kind of answer this is, before asking what the answer says."""

    DECIDED = "DECIDED"  # the rules ran; see `result`
    NOT_FOUND = "NOT_FOUND"  # no flight with that number on that date
    AMBIGUOUS = "AMBIGUOUS"  # several flights matched; see `options`
    UNRESOLVED = "UNRESOLVED"  # we could not get far enough to decide


@dataclass(frozen=True, slots=True)
class FlightOption:
    """One of several flights sharing a number on a date, for the customer to
    choose between."""

    key: str
    route: str
    scheduled_departure: datetime | None
    # Set when the options span more than one date. A daily rotation leaves at
    # the same clock time every day, so the time alone would print the same
    # words on every button and the customer would be choosing blind.
    show_date: bool = False

    @property
    def label(self) -> str:
        if self.scheduled_departure is None:
            when = "time unknown"
        else:
            at = self.scheduled_departure
            clock = at.strftime("%H:%M UTC")
            # Built by hand rather than with %-d, which is not portable.
            when = f"{at:%a} {at.day} {at:%b}, {clock}" if self.show_date else clock
        return f"{self.route}, departing {when}"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Everything the layers above need, and nothing they have to work out."""

    status: CheckStatus
    flight_number: str
    flight_date: date
    provider: str
    message: str | None = None
    flight: FlightFacts | None = None
    result: EligibilityResult | None = None
    options: tuple[FlightOption, ...] = ()
    raw: RawFlight | None = None

    @property
    def verdict(self) -> Verdict | None:
        """The verdict, where there is one.

        UNRESOLVED is NEEDS_REVIEW by definition: we could not decide, and the
        one thing we must never do is let that become a "no". NOT_FOUND and
        AMBIGUOUS have no verdict at all -- they are questions, not answers.
        """
        if self.status is CheckStatus.DECIDED:
            return self.result.verdict if self.result else None
        if self.status is CheckStatus.UNRESOLVED:
            return Verdict.NEEDS_REVIEW
        return None

    @property
    def needs_human_attention(self) -> bool:
        return self.verdict is Verdict.NEEDS_REVIEW


async def check(
    provider: FlightDataProvider,
    flight_number: str,
    flight_date: date,
    *,
    option_key: str | None = None,
) -> CheckResult:
    """Run one eligibility check.

    `option_key` answers the AMBIGUOUS case: the customer picks which of the
    matching flights was theirs and asks again.
    """
    number = flight_number.strip().upper()
    base = {
        "flight_number": number,
        "flight_date": flight_date,
        "provider": provider.name,
    }

    flow.open_block("CHECK REQUESTED", f"{number} · {flight_date.isoformat()}")
    flow.line("raw input", f"{flight_number!r}, {flight_date.isoformat()!r}")
    flow.line("provider", provider.name)
    if option_key:
        flow.line("chosen flight", option_key)

    try:
        records = await provider.fetch(number, flight_date)
    except FlightDataError as exc:
        flow.line("← FAILED", f"{type(exc).__name__}")
        flow.line("DECISION", "NEEDS_REVIEW — lookup failed, never a denial")
        # Every provider failure lands here, and every one becomes NEEDS_REVIEW.
        # An outage is not evidence about anybody's flight, and presenting it as
        # though it were would be the most expensive bug in the system.
        return CheckResult(
            status=CheckStatus.UNRESOLVED,
            message=_failure_message(exc),
            **base,  # type: ignore[arg-type]
        )

    if not records:
        flow.line("DECISION", "NOT_FOUND — a question, not a verdict")
        return CheckResult(
            status=CheckStatus.NOT_FOUND,
            message=(
                f"We could not find flight {number} on "
                f"{flight_date.isoformat()}. Please check the flight number and "
                f"the date -- the date is the day the flight departed."
            ),
            **base,  # type: ignore[arg-type]
        )

    if option_key is not None:
        records = [r for r in records if _option_key(r) == option_key]
        if not records:
            return CheckResult(
                status=CheckStatus.NOT_FOUND,
                message=(
                    f"That flight is no longer among the matches for {number} "
                    f"on {flight_date.isoformat()}. Please search again."
                ),
                **base,  # type: ignore[arg-type]
            )

    if len(records) > 1:
        # Never guess. Picking the first would tell everyone on the other
        # flight a confident answer about a journey they did not take.
        options = _build_options(records)
        flow.line("DECISION", f"AMBIGUOUS — {len(options)} matches, asking which")
        for option in options:
            flow.cont(option.label)
        return CheckResult(
            status=CheckStatus.AMBIGUOUS,
            options=options,
            message=(
                f"{len(options)} flights carried the number {number} on "
                f"{flight_date.isoformat()}. Which one were you on?"
            ),
            **base,  # type: ignore[arg-type]
        )

    record = records[0]
    mapped = to_flight_facts(record)
    if isinstance(mapped, MappingFailure):
        flow.line("normalised", "FAILED")
        for problem in mapped.problems:
            flow.cont(problem)
        flow.line("DECISION", "NEEDS_REVIEW — a gap in our data, not their flight")
        return CheckResult(
            status=CheckStatus.UNRESOLVED,
            message=mapped.reason,
            raw=record,
            **base,  # type: ignore[arg-type]
        )

    _log_facts(mapped)
    result = engine.evaluate(mapped)
    _log_rules(result)

    return CheckResult(
        status=CheckStatus.DECIDED,
        flight=mapped,
        result=result,
        raw=record,
        **base,  # type: ignore[arg-type]
    )


def _log_facts(flight: FlightFacts) -> None:
    """What the vendor's payload became.

    The point of showing this next to the raw response is that every
    enrichment is visible: which country an airport resolved to, which state
    licensed the carrier, and the distance we computed ourselves rather than
    taking from the provider.
    """
    flow.line(
        "normalised",
        f"{flight.origin_iata}({flight.origin_country}) → "
        f"{flight.destination_iata}({flight.destination_country})",
    )
    flow.cont(
        f"carrier {flight.airline_iata} licensed in {flight.airline_country}"
    )
    flow.cont(f"distance {flight.distance_km:,.0f} km (computed, not provided)")
    flow.cont(
        f"departure delay {flow.hours(flight.departure_delay_hours)}   "
        f"← Israeli law reads this"
    )
    flow.cont(
        f"arrival delay   {flow.hours(flight.arrival_delay_hours)}   "
        f"← EC261/UK261 read this"
    )
    flow.cont(f"status {flight.status.value}")


def _log_rules(result: engine.EligibilityResult) -> None:
    """Each law's answer, then the combined one.

    Logged from the outcomes rather than from inside the rules: the rules stay
    pure functions with no I/O, which is what makes them testable without
    mocks and is not worth giving up for a log line.
    """
    flow.header("rules")
    for outcome in result.outcomes:
        award = f"  {outcome.award}" if outcome.award else ""
        flow.cont(
            f"{outcome.regulation:<7} {outcome.verdict.value:<13}"
            f"applies={'yes' if outcome.applies else 'no ':<4}{award}"
        )
        flow.wrapped(outcome.reason)

    if result.best_award:
        flow.line(
            "DECISION",
            f"{result.verdict.value}  {result.best_award} under {result.best_regulation}",
        )
        if len(result.eligible_outcomes) > 1:
            others = ", ".join(
                f"{o.regulation} {o.award}" for o in result.eligible_outcomes[1:]
            )
            flow.cont(f"also payable: {others}")
    else:
        flow.line("DECISION", result.verdict.value)


def _build_options(records: Sequence[RawFlight]) -> tuple[FlightOption, ...]:
    """Label the matches so a human can tell them apart.

    Whether a date belongs on a label is a property of the whole set, not of
    any one option, so it is decided here rather than inside the label.
    """
    dates = {r.scheduled_departure.date() if r.scheduled_departure else None for r in records}
    show_date = len(dates) > 1
    return tuple(
        FlightOption(
            key=_option_key(r),
            route=r.route,
            scheduled_departure=r.scheduled_departure,
            show_date=show_date,
        )
        for r in records
    )


def _option_key(record: RawFlight) -> str:
    """A stable identifier for one of several matching flights.

    Route plus scheduled departure, because that is what actually distinguishes
    two flights sharing a number -- and unlike a list index it does not change
    if the provider returns them in a different order next time.
    """
    when = (
        record.scheduled_departure.strftime("%Y%m%dT%H%M")
        if record.scheduled_departure
        else "unknown"
    )
    return f"{record.origin_iata or '???'}-{record.destination_iata or '???'}-{when}"


def _failure_message(exc: FlightDataError) -> str:
    """What to tell the customer when the lookup itself failed.

    Never the exception text: it names vendors and status codes and helps
    nobody. The distinctions that survive are the ones that change what the
    customer should do next.
    """
    if isinstance(exc, ProviderRateLimited):
        return (
            "We have hit our limit for flight lookups just now. Your details "
            "have been saved and someone will check this shortly."
        )
    if isinstance(exc, ProviderAuthError):
        return (
            "We could not reach the flight database because of a problem on our "
            "side. Your details have been saved and someone will check this."
        )
    return (
        "The flight database did not respond. Your details have been saved and "
        "someone will check this shortly -- please do not assume you have no claim."
    )
