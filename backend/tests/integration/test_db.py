"""Tests for storing eligibility checks.

Against a real SQLite database, in memory. Not mocks: the whole point of these
tests is what SQLite does to our data on the way through, and a mock would agree
with whatever we already believed.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.models import EligibilityCheck
from app.db.repositories import (
    count_checks,
    find_others_on_the_same_flight,
    get_check,
    list_checks,
    record_check,
)
from app.db.session import (
    create_all,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from app.db.types import MoneyAmount, UtcDateTime
from app.domain.models import Verdict
from app.providers.registry import build_provider
from app.services.eligibility import CheckStatus, check

AUG_14 = date(2026, 8, 14)


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        yield session


async def store(session: Session, number: str, **kwargs: object) -> EligibilityCheck:
    outcome = await check(build_provider("fake"), number, AUG_14)
    return record_check(session, outcome, **kwargs)  # type: ignore[arg-type]


# --- What SQLite would otherwise do to our data ------------------------------


async def test_money_survives_the_round_trip_exactly(session: Session) -> None:
    """The single most important test in this file.

    SQLite has no decimal type. Stored as a float, 520.00 can come back as
    519.9999999999999 -- the same mistake `Money` exists to prevent, one layer
    down. MoneyAmount stores an exact integer number of minor units instead.
    """
    row = await store(session, "BA165")
    session.expire_all()  # force a real read back from the database

    reloaded = get_check(session, row.id)
    assert reloaded is not None
    assert reloaded.best_amount == Decimal("520.00")
    assert isinstance(reloaded.best_amount, Decimal)
    assert reloaded.best_currency == "GBP"


async def test_timestamps_come_back_timezone_aware(session: Session) -> None:
    """SQLite discards the offset.

    A naive timestamp compared against an aware one raises; two naive ones from
    different zones silently give a wrong answer. That is exactly the bug
    FlightFacts refuses to allow, so the column type reattaches UTC on the way
    out.
    """
    row = await store(session, "BA165")
    session.expire_all()

    reloaded = get_check(session, row.id)
    assert reloaded is not None
    assert reloaded.created_at.tzinfo is not None
    assert reloaded.created_at.utcoffset() is not None


def test_storing_a_naive_timestamp_is_refused() -> None:
    """Loudly, at the boundary, naming the value."""
    with pytest.raises(ValueError, match="naive timestamp"):
        UtcDateTime().process_bind_param(datetime(2026, 8, 14, 12, 0), None)  # type: ignore[arg-type]


def test_a_local_timestamp_is_normalised_to_utc(session: Session) -> None:
    """Everything in the database is UTC by construction, so two rows written
    from different timezones are still comparable."""
    from datetime import timedelta, timezone

    stored = UtcDateTime().process_bind_param(
        datetime(2026, 8, 14, 12, 0, tzinfo=timezone(timedelta(hours=3))), None  # type: ignore[arg-type]
    )
    assert stored == datetime(2026, 8, 14, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("amount", "minor"), [("520.00", 52000), ("0.01", 1), ("3670.00", 367000)]
)
def test_amounts_are_stored_as_exact_minor_units(amount: str, minor: int) -> None:
    kind = MoneyAmount()
    assert kind.process_bind_param(Decimal(amount), None) == minor  # type: ignore[arg-type]
    assert kind.process_result_value(minor, None) == Decimal(amount)  # type: ignore[arg-type]


# --- Every check is recorded -------------------------------------------------


@pytest.mark.parametrize(
    ("number", "expected_status"),
    [
        ("BA165", CheckStatus.DECIDED),      # eligible
        ("LY325", CheckStatus.DECIDED),      # not eligible
        ("XX999", CheckStatus.NOT_FOUND),    # no such flight
        ("ERR503", CheckStatus.UNRESOLVED),  # provider down
        ("FR1234", CheckStatus.AMBIGUOUS),   # which one was yours
        ("ZZ999", CheckStatus.UNRESOLVED),   # gap in our reference data
    ],
)
async def test_every_kind_of_answer_is_stored(
    session: Session, number: str, expected_status: CheckStatus
) -> None:
    """Including the ones that concluded nothing.

    Storing only the eligible checks would throw away the review queue, the
    record of what the customer was actually told, and any way to notice that a
    provider has started failing.
    """
    row = await store(session, number)
    assert row.status == expected_status.value
    assert row.id is not None


async def test_a_not_eligible_check_stores_no_amount(session: Session) -> None:
    row = await store(session, "LY325")
    assert row.verdict == Verdict.NOT_ELIGIBLE.value
    assert row.best_amount is None
    assert row.best_regulation is None


async def test_a_failed_lookup_is_stored_as_needing_review(session: Session) -> None:
    """Never as a denial -- not even in the database, where a later report would
    read it back as one."""
    row = await store(session, "ERR503")
    assert row.verdict == Verdict.NEEDS_REVIEW.value
    assert row.message is not None and "do not assume" in row.message


# --- The evidence ------------------------------------------------------------


async def test_the_flight_snapshot_records_what_the_verdict_was_based_on(
    session: Session,
) -> None:
    """So a decision can be re-explained months later, and re-run against a
    corrected rule without paying for the lookup again."""
    row = await store(session, "BA165")
    snapshot = row.flight_snapshot
    assert snapshot is not None
    assert snapshot["origin_iata"] == "TLV"
    assert snapshot["destination_country"] == "GB"
    assert snapshot["arrival_delay_hours"] == 4.0
    assert snapshot["distance_km"] == pytest.approx(3588.6, abs=1.0)


async def test_the_snapshot_is_json_safe(session: Session) -> None:
    """Dates, decimals and enums all need a representation that survives a round
    trip through JSON without becoming something else."""
    import json

    row = await store(session, "BA165")
    assert json.loads(json.dumps(row.flight_snapshot))["flight_date"] == "2026-08-14"
    assert json.loads(json.dumps(row.result_detail))["verdict"] == "ELIGIBLE"


async def test_all_three_regulations_reasoning_is_stored(session: Session) -> None:
    """Not just the winner.

    "Why did it say no?" six months from now must have an answer that does not
    depend on the rules still being what they were.
    """
    row = await store(session, "BA165")
    detail = row.result_detail
    assert detail is not None
    assert {o["regulation"] for o in detail["outcomes"]} == {
        "EC261",
        "UK261",
        "ISRAEL",
    }
    assert all(o["reason"] for o in detail["outcomes"])


async def test_the_untouched_provider_payload_is_kept(session: Session) -> None:
    row = await store(session, "BA165")
    assert row.provider_payload is not None
    assert row.provider == "fake"


# --- Contact details ---------------------------------------------------------


async def test_contact_details_are_normalised(session: Session) -> None:
    """Emails are matched on later, so they are stored one way."""
    row = await store(
        session, "BA165", contact_name="  Noam Hasson ", contact_email=" N@Example.COM "
    )
    assert row.contact_name == "Noam Hasson"
    assert row.contact_email == "n@example.com"


async def test_contact_details_are_optional(session: Session) -> None:
    """The first thing a visitor does is check a flight. Demanding a name before
    answering would lose most of them."""
    row = await store(session, "BA165")
    assert row.contact_name is None
    assert row.contact_email is None


# --- Reading it back ---------------------------------------------------------


async def test_checks_are_listed_newest_first(session: Session) -> None:
    for number in ("BA165", "LY325", "XX999"):
        await store(session, number)
    session.flush()

    rows = list_checks(session)
    assert len(rows) == 3
    assert rows[0].created_at >= rows[-1].created_at


async def test_the_review_queue_can_be_filtered(session: Session) -> None:
    """The query an operator actually runs every morning."""
    for number in ("BA165", "LY325", "ERR503", "ZZ999"):
        await store(session, number)
    session.flush()

    review = list_checks(session, verdict=Verdict.NEEDS_REVIEW.value)
    assert len(review) == 2
    assert count_checks(session, verdict=Verdict.NEEDS_REVIEW.value) == 2


async def test_listing_is_paginated(session: Session) -> None:
    """Unbounded listings are fine on day one and a problem on day four
    hundred, by which time they live in a dashboard nobody wants to touch."""
    for _ in range(5):
        await store(session, "BA165")
    session.flush()

    assert len(list_checks(session, limit=2)) == 2
    assert len(list_checks(session, limit=2, offset=4)) == 1


async def test_checks_can_be_found_by_flight(session: Session) -> None:
    await store(session, "BA165")
    await store(session, "LY325")
    session.flush()

    assert len(list_checks(session, flight_number="ba165")) == 1
    assert len(list_checks(session, flight_number="BA165", flight_date=AUG_14)) == 1
    assert len(list_checks(session, flight_number="BA165", flight_date=date(2020, 1, 1))) == 0


async def test_other_passengers_on_the_same_flight_can_be_found(
    session: Session,
) -> None:
    """Several passengers on one disrupted flight usually check separately.

    They belong in one claim: cheaper to run, and far stronger against the
    airline than the same facts argued five times.
    """
    first = await store(session, "BA165", contact_email="a@example.com")
    await store(session, "BA165", contact_email="b@example.com")
    await store(session, "LY325", contact_email="c@example.com")
    session.flush()

    others = find_others_on_the_same_flight(session, first)
    assert len(others) == 1
    assert others[0].contact_email == "b@example.com"


async def test_an_unknown_id_returns_none(session: Session) -> None:
    assert get_check(session, uuid.uuid4()) is None


async def test_ids_are_uuids_not_sequential_integers(session: Session) -> None:
    """A sequential id in a URL tells every customer how many checks have been
    run, and lets them read the next one by adding 1."""
    row = await store(session, "BA165")
    assert isinstance(row.id, uuid.UUID)


# --- Transactions ------------------------------------------------------------


def test_a_failed_transaction_rolls_back() -> None:
    """A half-written check is worse than no check: it looks like an answer."""
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    factory = create_session_factory(engine)

    with pytest.raises(RuntimeError):
        with session_scope(factory) as session:
            session.add(
                EligibilityCheck(
                    flight_number="BA165", flight_date=AUG_14,
                    status="DECIDED", provider="fake",
                )
            )
            session.flush()
            raise RuntimeError("something went wrong downstream")

    with session_scope(factory) as session:
        assert count_checks(session) == 0


async def test_a_decided_review_still_gets_a_readable_summary(
    session: Session,
) -> None:
    """A cancelled flight is DECIDED with an open question, so it carries no
    service-level message of its own.

    Without a summary the row shows a blank line next to it. The open question
    is in result_detail either way, but a list nobody can skim is a list nobody
    works.
    """
    row = await store(session, "LH687")
    assert row.status == CheckStatus.DECIDED.value
    assert row.verdict == Verdict.LIKELY_ELIGIBLE.value
    assert row.message is not None
    assert "14 days" in row.message


async def test_a_decided_verdict_does_not_invent_a_summary(session: Session) -> None:
    """Nothing needs attention, so there is nothing to say."""
    assert (await store(session, "BA165")).message is None
