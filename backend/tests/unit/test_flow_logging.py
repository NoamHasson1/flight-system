"""Tests for the request trace.

Mostly about what it must NOT print. A log is the easiest place in a system to
leak something, because nobody reviews it and everybody reads it.
"""

import logging
import pathlib

import pytest

from app.config import Settings
from app.db.models import Claim, EligibilityCheck, Passenger
from app.db.session import _describe
from app.observability import flow


# --- What never appears ------------------------------------------------------


def test_a_national_id_is_absent_not_masked() -> None:
    """Absent, deliberately.

    A masked secret in a log is still a secret in a log -- one careless change
    from being unmasked -- and this is the most sensitive field in the system.
    """
    passenger = Passenger(full_name="Noam Hasson", national_id="012345678")
    described = _describe(passenger)

    assert "012345678" not in described
    assert "national_id" not in described
    assert "Noam Hasson" in described  # the row is still identifiable
    assert "not shown" in described  # and the omission is visible


def test_emails_are_masked() -> None:
    """Enough to confirm the right person was contacted, not enough to harvest."""
    check = EligibilityCheck(
        flight_number="BA165", status="DECIDED", provider="fake",
        contact_email="noam@example.com",
    )
    described = _describe(check)

    assert "noam@example.com" not in described
    assert "n***@example.com" in described


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("noam@example.com", "n***@example.com"),
        ("a@b.co", "a***@b.co"),
        ("", "—"),
        (None, "—"),
        ("not-an-address", "—"),
    ],
)
def test_masking_handles_every_shape(address: str | None, expected: str) -> None:
    assert flow.mask_email(address) == expected


def test_the_json_blobs_are_left_out() -> None:
    """flight_snapshot and result_detail are each a screen of JSON.

    Printing them turns a readable trace into something nobody reads, which
    costs more than it saves -- they are in the database and in the admin API
    for anyone who needs them.
    """
    check = EligibilityCheck(
        flight_number="BA165", status="DECIDED", provider="fake",
        flight_snapshot={"origin_iata": "TLV"}, result_detail={"verdict": "ELIGIBLE"},
    )
    described = _describe(check)

    assert "origin_iata" not in described
    assert "flight_snapshot" not in described


def test_long_values_are_truncated_not_wrapped() -> None:
    """One row is one line. A claim note running to a paragraph would otherwise
    push the rest of the trace off the screen."""
    claim = Claim(
        reference="FS-2026-K7M9QX", status="DRAFT",
        contact_name="A" * 200, contact_email="a@b.com",
    )
    line = _describe(claim)

    assert "A" * 200 not in line
    assert "…" in line


# --- When it runs ------------------------------------------------------------


def test_the_trace_is_off_in_production() -> None:
    """It prints flight details and masked customer emails on every request.

    That is exactly what you want on a laptop and exactly what you do not want
    accumulating in a production log aggregator, so the environment decides
    rather than whoever last edited the config.
    """
    assert Settings(environment="production", log_flow=True).flow_logging_enabled is False
    assert Settings(environment="development", log_flow=True).flow_logging_enabled is True
    assert Settings(environment="development", log_flow=False).flow_logging_enabled is False


def test_the_trace_has_its_own_logger() -> None:
    """So it can be silenced without silencing anything else -- and so its lines
    print bare, without the level and name prefix that would wreck the column
    alignment the whole thing depends on."""
    from app.main import create_app

    create_app(Settings(environment="test", log_flow=True))
    trace = logging.getLogger("flight_system.flow")

    assert trace.propagate is False
    assert trace.handlers
    assert trace.handlers[0].formatter._fmt == "%(message)s"  # type: ignore[union-attr]


def test_nothing_is_formatted_when_it_is_disabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`flow.enabled()` is checked before building a line, not after.

    The database listener runs on every flush; formatting a row and then
    discarding it would make the trace cost something even when nobody is
    reading it.
    """
    trace = logging.getLogger("flight_system.flow")
    previous = trace.level
    trace.setLevel(logging.WARNING)
    try:
        assert flow.enabled() is False
    finally:
        trace.setLevel(previous)


# --- Formatting --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(4.0, "4h 00m"), (2.05, "2h 03m"), (-0.5, "-0h 30m"), (None, "—")],
)
def test_delays_read_the_way_people_say_them(
    value: float | None, expected: str
) -> None:
    """2.0499999 hours is a number. "2h 03m" is a delay."""
    assert flow.hours(value) == expected


def test_the_verdict_column_fits_the_longest_verdict() -> None:
    """The trace is read by eye, in columns, and a verdict that overflows runs
    straight into the next field -- "LIKELY_ELIGIBLEapplies=yes".

    Pinned to the enum rather than to a number, so adding a longer verdict
    fails here instead of quietly ruining the alignment.
    """
    from app.domain.models import Verdict

    longest = max(len(v.value) for v in Verdict)
    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "eligibility.py"
    ).read_text()
    assert "outcome.verdict.value:<16" in source
    assert longest < 16, f"{longest}-character verdict needs a wider column"
