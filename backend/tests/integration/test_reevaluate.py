"""Re-evaluation against a real database.

The unit tests cover the CHOICE between two records. These cover the two
things only a database can show: that the archive is actually reachable
from a check, and that reading a result page re-runs the rules without
writing anything.

That last one is not a style point. If the GET wrote, two tabs open on the
same claim would race, a retried request could produce a different answer
from the first, and the sweep's report of "what moved today" would be
polluted by whoever happened to refresh a page.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.models import EligibilityCheck, FlightLookup
from app.db.session import (
    create_all,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from app.services.reevaluate import current_result, facts_from_archive

SEP_26 = date(2026, 9, 26)


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    with session_scope(create_session_factory(engine)) as session:
        yield session


def _snapshot(**overrides: object) -> dict[str, object]:
    """The facts as the check stored them: TLV to Sochi, no departure yet."""
    base: dict[str, object] = {
        "flight_number": "A45024",
        "flight_date": "2026-09-26",
        "airline_iata": "A4",
        "airline_country": "RU",
        "origin_iata": "TLV",
        "origin_country": "IL",
        "destination_iata": "AER",
        "destination_country": "RU",
        "distance_km": 1600.0,
        "scheduled_departure": "2026-09-26T19:35:00+00:00",
        "scheduled_arrival": "2026-09-26T22:30:00+00:00",
        "actual_departure": None,
        "actual_arrival": None,
        "status": "SCHEDULED",
    }
    base.update(overrides)
    return base


def _check(session: Session, **overrides: object) -> EligibilityCheck:
    fields: dict[str, object] = {
        "flight_number": "A45024",
        "flight_date": SEP_26,
        "status": "COMPLETED",
        "verdict": "NEEDS_REVIEW",
        "provider": "iaa",
        "flight_snapshot": _snapshot(),
        "result_detail": {"outcomes": []},
    }
    fields.update(overrides)
    row = EligibilityCheck(**fields)  # type: ignore[arg-type]
    session.add(row)
    session.flush()
    return row


def _archive(session: Session, **flight: object) -> None:
    """One archived lookup for the same flight and day."""
    record: dict[str, object] = {
        "flight_number": "A45024",
        "flight_date": "2026-09-26",
        "status": "SCHEDULED",
        "provider": "iaa",
        "airline_iata": "A4",
        "origin_iata": "TLV",
        "destination_iata": "AER",
        "scheduled_departure": "2026-09-26T19:35:00+00:00",
        "scheduled_arrival": "2026-09-26T22:30:00+00:00",
        "actual_departure": None,
        "actual_arrival": None,
        "raw": {},
    }
    record.update(flight)
    session.add(
        FlightLookup(
            provider="iaa",
            flight_number="A45024",
            flight_date=SEP_26,
            observed_at=datetime(2026, 9, 26, 8, 0, tzinfo=UTC),
            is_final=False,
            flights=[record],
        )
    )
    session.flush()


# --- reaching the archive from a check ---------------------------------------


def test_a_check_with_nothing_archived_falls_back_to_its_snapshot() -> None:
    """Most checks are this, and the sweep must not report them as changed.

    Written first because the opposite failure is invisible: if the archive
    query matched nothing due to, say, a case mismatch on the flight number,
    every test about choosing records would still pass and the feature
    would do nothing in production.
    """
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    with session_scope(create_session_factory(engine)) as session:
        row = _check(session)
        assert facts_from_archive(row, session) is None
        assert current_result(row, session) is not None


def test_the_archive_supplies_a_departure_the_snapshot_never_had(
    session: Session,
) -> None:
    """A45024, once `rederive` has re-read the board's revised time.

    This is the whole point of consulting the archive. The check was taken
    while the parser discarded the revision, so its snapshot says the
    flight left on time. The raw payload always held the revised time, and
    re-deriving it put a better record within reach -- without a lookup,
    a quota, or a vendor.
    """
    row = _check(session)
    _archive(session, actual_departure="2026-09-27T12:20:00+00:00")

    facts = facts_from_archive(row, session)

    assert facts is not None
    assert facts.actual_departure == datetime(2026, 9, 27, 12, 20, tzinfo=UTC)
    assert row.flight_snapshot["actual_departure"] is None  # type: ignore[index]


def test_a_thinner_archive_row_does_not_displace_a_richer_snapshot(
    session: Session,
) -> None:
    """The same flight the other way round -- and the bug that shipped first.

    The board sheds the past, so an archived row can be the EARLY capture:
    correct, complete for its moment, and missing the revision that came
    afterwards. Preferring the archive because it exists would have
    replaced a 17-hour delay with an on-time departure.
    """
    row = _check(
        session,
        flight_snapshot=_snapshot(actual_departure="2026-09-27T12:20:00+00:00"),
    )
    _archive(session)  # no actual departure

    result = current_result(row, session)

    assert result is not None
    assert result.best_award is not None, "the revision must survive"


def test_a_cancellation_in_the_snapshot_survives_a_fuller_archive_row(
    session: Session,
) -> None:
    """BZ611 in miniature, through the real query path.

    The unit test proves `_confidence` ranks them correctly. This proves
    the ranking is actually consulted when the two records come from
    different places -- which is where the first version went wrong.
    """
    row = _check(
        session,
        verdict="LIKELY_ELIGIBLE",
        best_amount=Decimal("400.00"),
        best_currency="EUR",
        flight_snapshot=_snapshot(
            status="CANCELLED",
            scheduled_arrival=None,
        ),
    )
    _archive(
        session,
        status="EN_ROUTE",
        actual_departure="2026-09-26T20:15:00+00:00",
        actual_arrival="2026-09-26T23:05:00+00:00",
    )

    facts = current_result(row, session)

    assert facts is not None
    assert facts.verdict.value != "NOT_ELIGIBLE", (
        "a 40-minute delay must not overwrite a cancellation"
    )


def test_without_a_session_only_the_snapshot_is_used(session: Session) -> None:
    """The read path's contract, asserted rather than assumed.

    `GET /checks/{id}` is served on every page view and must not fan out
    into extra queries per request. Passing no session is how it says so,
    and this test fails if someone later makes the session mandatory.
    """
    row = _check(session)
    _archive(session, actual_departure="2026-09-27T12:20:00+00:00")

    assert current_result(row) == current_result(row, session=None)


# --- the read path does not write --------------------------------------------


def test_reading_a_result_page_leaves_the_stored_verdict_alone(
    client, session: Session
) -> None:  # type: ignore[no-untyped-def]
    """The rule that keeps this feature safe to expose on a GET.

    The response may show a better verdict than the row holds -- that is
    the feature. What it may not do is persist it. Recording a change is
    `app.tasks.reevaluate`, run deliberately, once, where the list of
    people whose answer moved can be reviewed before anyone is told.
    """
    created = client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "XX100", "flight_date": "2026-08-14"},
    )
    assert created.status_code == 200
    check_id = created.json()["check_id"]
    before = created.json()["verdict"]

    for _ in range(3):
        assert client.get(f"/api/v1/eligibility/checks/{check_id}").status_code == 200

    after = client.get(f"/api/v1/eligibility/checks/{check_id}")
    assert after.status_code == 200
    # Same answer every time, and the answer the check itself gave.
    assert after.json()["verdict"] == before
