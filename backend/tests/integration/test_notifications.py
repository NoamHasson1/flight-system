"""Tests for deciding what to send, and for the endpoints that send it.

The adapters are tested alone in tests/unit/test_email.py. These cover the
rules: who gets an email, who does not, and what happens when the mail server
is down.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.claims import add_passenger, create_claim, submit_claim
from app.db.repositories import record_check
from app.db.session import (
    create_all,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from app.email.base import EmailMessage, EmailSender
from app.providers.registry import build_provider
from app.services.eligibility import check as run_check
from app.services.notifications import send_check_result, send_claim_confirmation

AUG_14 = date(2026, 8, 14)


class Recorder:
    """An in-memory sender. Satisfies `EmailSender`."""

    name = "recorder"

    def __init__(self, succeed: bool = True) -> None:
        self.sent: list[EmailMessage] = []
        self.succeed = succeed

    def send(self, message: EmailMessage) -> bool:
        if not self.succeed:
            return False
        self.sent.append(message)
        return True


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    with session_scope(create_session_factory(engine)) as session:
        yield session


async def a_claim(session: Session, number: str = "BA165", **kwargs: object):  # type: ignore[no-untyped-def]
    outcome = await run_check(build_provider("fake"), number, AUG_14)
    check = record_check(session, outcome)
    claim = create_claim(
        session, check, contact_name="Noam Hasson",
        contact_email="noam@example.com", **kwargs,  # type: ignore[arg-type]
    )
    add_passenger(session, claim, full_name="Noam Hasson")
    return claim


def test_the_recorder_satisfies_the_contract() -> None:
    assert isinstance(Recorder(), EmailSender)


# --- The confirmation -------------------------------------------------------


async def test_a_submitted_claim_gets_a_confirmation(session: Session) -> None:
    """Somebody has just handed over their passengers' identity numbers and
    their receipts, and the only thing they have to show for it is a reference
    on a screen they are about to close. This is the receipt."""
    claim = await a_claim(session)
    submit_claim(session, claim)
    sender = Recorder()

    assert send_claim_confirmation(sender, claim, base_url="https://x.test") is True

    message = sender.sent[0]
    assert message.to == "noam@example.com"
    assert claim.reference in message.subject
    assert claim.reference in message.text


async def test_it_is_never_sent_twice(session: Session) -> None:
    """A customer who gets the same confirmation three times stops trusting the
    next email we send -- which is the one telling them the airline paid.

    Idempotency matters here because a retried request, a double-clicked Submit
    and a replayed background task all reach this function.
    """
    claim = await a_claim(session)
    submit_claim(session, claim)
    sender = Recorder()

    assert send_claim_confirmation(sender, claim, base_url="https://x.test") is True
    assert send_claim_confirmation(sender, claim, base_url="https://x.test") is False
    assert len(sender.sent) == 1


async def test_a_failed_send_is_not_recorded_as_sent(session: Session) -> None:
    """So a retry can pick it up later.

    Recording a failed send would lose that email for good, and nobody would
    ever notice -- the row would say it went.
    """
    claim = await a_claim(session)
    submit_claim(session, claim)

    assert send_claim_confirmation(Recorder(succeed=False), claim, base_url="https://x.test") is False
    assert claim.confirmation_sent_at is None

    assert send_claim_confirmation(Recorder(), claim, base_url="https://x.test") is True
    assert claim.confirmation_sent_at is not None


async def test_the_confirmation_carries_the_flight_and_the_amount(
    session: Session,
) -> None:
    claim = await a_claim(session)
    submit_claim(session, claim)
    sender = Recorder()
    send_claim_confirmation(sender, claim, base_url="https://x.test")

    text = sender.sent[0].text
    assert "BA165" in text
    assert "TLV → LHR" in text
    assert "£520.00" in text


# --- The result email -------------------------------------------------------


async def test_no_result_email_without_an_address(session: Session) -> None:
    """The check form does not require one, so an address means somebody typed
    it deliberately. A result email nobody asked for is spam however useful we
    happen to think it is."""
    outcome = await run_check(build_provider("fake"), "BA165", AUG_14)
    check = record_check(session, outcome)  # no contact_email
    sender = Recorder()

    assert send_check_result(sender, check, base_url="https://x.test") is False
    assert sender.sent == []


async def test_a_result_email_is_sent_when_asked(session: Session) -> None:
    outcome = await run_check(build_provider("fake"), "BA165", AUG_14)
    check = record_check(session, outcome, contact_email="noam@example.com")
    sender = Recorder()

    assert send_check_result(sender, check, base_url="https://x.test") is True
    assert "£520.00" in sender.sent[0].subject


@pytest.mark.parametrize("number", ["XX999", "FR1234"])
async def test_questions_are_not_emailed(session: Session, number: str) -> None:
    """NOT_FOUND and AMBIGUOUS are questions, not answers.

    Emailing "we could not find your flight" to somebody still sitting in front
    of the form is noise, and noise is how a sender's reputation goes.
    """
    outcome = await run_check(build_provider("fake"), number, AUG_14)
    check = record_check(session, outcome, contact_email="noam@example.com")
    sender = Recorder()

    assert send_check_result(sender, check, base_url="https://x.test") is False


async def test_the_link_points_at_the_configured_host(session: Session) -> None:
    """A background task has no request to read the host from, and behind a
    proxy the request's host is the proxy's anyway."""
    outcome = await run_check(build_provider("fake"), "BA165", AUG_14)
    check = record_check(session, outcome, contact_email="noam@example.com")
    sender = Recorder()
    send_check_result(sender, check, base_url="https://claims.example.com/")

    assert f"https://claims.example.com/check/{check.id}" in sender.sent[0].text


# --- Through the API --------------------------------------------------------


def test_submitting_a_claim_over_http_sends_the_confirmation(
    client: TestClient,
) -> None:
    """End to end, including the background task.

    TestClient runs background tasks after the response, which is exactly the
    ordering the real server uses -- so this also proves the task can open its
    own session after the request's has been torn down.
    """
    from app.api.deps import get_email_sender

    sender = Recorder()
    client.app.dependency_overrides[get_email_sender] = lambda: sender  # type: ignore[attr-defined]

    check = client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": "2026-08-14"},
    ).json()
    claim = client.post(
        "/api/v1/claims",
        json={
            "check_id": check["check_id"], "contact_name": "Noam Hasson",
            "contact_email": "noam@example.com",
            "passengers": [{"full_name": "Noam Hasson"}],
        },
    ).json()

    response = client.post(f"/api/v1/claims/{claim['id']}/submit")

    assert response.status_code == 200
    assert len(sender.sent) == 1
    assert claim["reference"] in sender.sent[0].subject


def test_a_dead_mail_server_does_not_fail_the_submission(
    client: TestClient,
) -> None:
    """The most important test in this file.

    A customer who submits a claim and sees an error because our mail server is
    down will assume it did not go through, and will either give up or submit
    it twice. The claim is the valuable thing; the email is a courtesy.
    """
    from app.api.deps import get_email_sender

    class Exploding:
        name = "exploding"

        def send(self, message: EmailMessage) -> bool:
            raise RuntimeError("the mail server is on fire")

    client.app.dependency_overrides[get_email_sender] = lambda: Exploding()  # type: ignore[attr-defined]

    check = client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": "2026-08-14"},
    ).json()
    claim = client.post(
        "/api/v1/claims",
        json={
            "check_id": check["check_id"], "contact_name": "Noam Hasson",
            "contact_email": "noam@example.com",
            "passengers": [{"full_name": "Noam Hasson"}],
        },
    ).json()

    response = client.post(f"/api/v1/claims/{claim['id']}/submit")

    assert response.status_code == 200
    assert response.json()["status"] == "SUBMITTED"


def test_a_check_with_an_email_gets_one(client: TestClient) -> None:
    from app.api.deps import get_email_sender

    sender = Recorder()
    client.app.dependency_overrides[get_email_sender] = lambda: sender  # type: ignore[attr-defined]

    client.post(
        "/api/v1/eligibility/check",
        json={
            "flight_number": "BA165", "flight_date": "2026-08-14",
            "contact_email": "noam@example.com",
        },
    )

    assert len(sender.sent) == 1
    assert "BA165" in sender.sent[0].subject


def test_a_check_without_an_email_gets_none(client: TestClient) -> None:
    from app.api.deps import get_email_sender

    sender = Recorder()
    client.app.dependency_overrides[get_email_sender] = lambda: sender  # type: ignore[attr-defined]

    client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": "2026-08-14"},
    )

    assert sender.sent == []
