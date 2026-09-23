"""Tests for deciding what to send, and for the endpoints that send it.

The adapters are tested alone in tests/unit/test_email.py. These cover the
rules: who gets an email, who does not, and what happens when the mail server
is down.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
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
from app.services.notifications import (
    notify_ops_check,
    notify_ops_claim,
    ops_reference,
    send_check_result,
    send_claim_confirmation,
)

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


# --- The company's own copy --------------------------------------------------
#
# A different reader from the customer: whoever runs this, deciding what to do
# today, working from an inbox rather than a database. The person who chases an
# airline is not the person who writes SQL.


async def test_the_subject_line_carries_the_whole_story(session: Session) -> None:
    """A mailbox is read as a list of subjects, sorted and searched by them.

    "New claim" tells nobody anything. The verdict, the amount, the flight and
    the name mean the inbox is usable without opening a single message.

    Asked of the CLAIM, because that is where an eligible customer's one email
    now comes from -- the check that preceded it is deliberately silent.
    """
    sender = Recorder()
    claim = await a_claim(session)

    notify_ops_claim(sender, claim, to="ops@example.com", base_url="http://x")

    subject = sender.sent[0].subject
    assert "ELIGIBLE" in subject
    assert "BA165" in subject
    assert "£" in subject or "€" in subject, "the amount is what makes it scannable"


async def test_a_claim_carries_everything_needed_to_act(session: Session) -> None:
    """Self-contained on purpose: nobody should have to open the system to
    understand what arrived."""
    sender = Recorder()
    claim = await a_claim(session)

    notify_ops_claim(sender, claim, to="ops@example.com", base_url="http://x")

    body = sender.sent[0].text
    assert claim.reference in body
    assert claim.contact_email in body
    # Grouped the way it will be used, not as one run-on list: somebody is
    # about to write to an airline from this and needs to find one fact fast.
    assert "WHO TO REPLY TO" in body
    assert "THE CLAIM" in body
    assert "PASSENGERS" in body
    assert "OUT OF POCKET" in body


async def test_identity_numbers_never_reach_the_inbox(session: Session) -> None:
    """THE test in this section.

    They are encrypted at rest for a reason, and an inbox is the opposite of
    that: unencrypted, forwarded, backed up by a mail provider, searchable
    forever. One line copying them out would undo the whole of that work.

    The passenger count makes it obvious the numbers were collected; the
    numbers themselves stay where they are protected.
    """
    sender = Recorder()
    claim = await a_claim(session)
    claim.passengers[0].national_id = "312345678"
    session.flush()

    notify_ops_claim(sender, claim, to="ops@example.com", base_url="http://x")

    message = sender.sent[0]
    assert "312345678" not in message.text
    assert "312345678" not in message.html
    assert "PASSENGERS (1)" in message.text, "the count should still be visible"


async def test_no_company_address_means_no_email(session: Session) -> None:
    """Empty is a deliberate off switch, right for a laptop and wrong for a
    deployment -- and it must not become a send to the empty string."""
    sender = Recorder()
    claim = await a_claim(session)

    assert notify_ops_check(sender, claim.check, to="", base_url="http://x") is False
    assert notify_ops_check(sender, claim.check, to=" ", base_url="http://x") is False
    assert sender.sent == []


async def test_a_flight_we_could_not_identify_is_still_reported(
    session: Session,
) -> None:
    """A check that found nothing is still the company's business -- and is
    where a missing airline or a broken source shows up first."""
    sender = Recorder()
    claim = await a_claim(session, "ZZ999")

    assert notify_ops_check(
        sender, claim.check, to="ops@example.com", base_url="http://x"
    )
    assert sender.sent[0].subject


async def test_the_subject_leads_with_the_customer_s_name(session: Session) -> None:
    """Because that is what anybody searches a mailbox for.

    Somebody rings up and gives their name; you type it into the search box
    and their claim is there. A subject that leads with a flight number is
    searchable only by people who already know the flight number.
    """
    sender = Recorder()
    claim = await a_claim(session)

    notify_ops_claim(sender, claim, to="ops@example.com", base_url="http://x")

    subject = sender.sent[0].subject
    assert subject.index("Noam Hasson") < subject.index("BA165"), subject


async def test_a_check_with_no_name_leads_with_the_flight(session: Session) -> None:
    """The first screen asks for a flight number and a date and nothing else,
    so most checks have no name attached.

    It says the flight rather than inventing an "Unknown", which would sort
    every anonymous check into one indistinguishable pile.

    LY325 rather than BA165: an anonymous check only reaches the inbox when it
    is the end of the journey, and BA165 qualifies.
    """
    sender = Recorder()
    claim = await a_claim(session, "LY325")
    claim.check.contact_name = None

    notify_ops_check(sender, claim.check, to="ops@example.com", base_url="http://x")

    subject = sender.sent[0].subject
    assert "LY325" in subject
    assert "Unknown" not in subject and "Anonymous" not in subject


async def test_a_flight_that_does_not_qualify_is_four_lines(session: Session) -> None:
    """There is nothing to do about it, so there is nothing to read.

    Length is how an inbox stops being read. A claim earns a long message; a
    check that came to nothing earns who, which flight, and why not.
    """
    sender = Recorder()
    claim = await a_claim(session, "LY325")

    notify_ops_check(sender, claim.check, to="ops@example.com", base_url="http://x")

    body = sender.sent[0].text
    assert "NOT ELIGIBLE" in sender.sent[0].subject
    assert len([line for line in body.splitlines() if line.strip()]) <= 6, body


# --- One email per customer --------------------------------------------------
#
# The rule: a person produces ONE row in the company's inbox, at the END of
# their journey. A "no" ends it at the result screen, so that is where their
# email comes from. A "yes" does not -- they are on their way to the claim
# form, which produces a message containing everything this one would have
# said. Sending both would mean two rows for one person, and an inbox where a
# row is not a person is an inbox nobody can work from.
#
# These are written against the OBSERVABLE behaviour -- what arrives and what
# does not -- rather than against the predicate, because the predicate is an
# implementation detail and "how many emails did that customer generate" is
# the thing that was actually asked for.


@pytest.mark.parametrize(
    ("number", "verdict"),
    [("LY325", "NOT_ELIGIBLE"), ("ZZ999", "NEEDS_REVIEW")],
)
async def test_an_ending_verdict_is_emailed_immediately(
    session: Session, number: str, verdict: str
) -> None:
    """Nothing else is coming, so this is the message.

    NEEDS_REVIEW is here for a different reason than NOT_ELIGIBLE: it is not
    the customer's answer but OUR failure -- a carrier missing from
    airlines.csv, an airport we do not recognise. Waiting for a submission that
    may never come would make us blind to our own data gaps, and this email is
    exactly how forty-three missing carriers were found.
    """
    sender = Recorder()
    claim = await a_claim(session, number)
    assert claim.check.verdict == verdict, "the fixture no longer tests what it says"

    assert notify_ops_check(
        sender, claim.check, to="ops@example.com", base_url="http://x"
    )
    assert len(sender.sent) == 1


@pytest.mark.parametrize("number", ["BA165", "LH687"])
async def test_a_qualifying_check_is_silent(session: Session, number: str) -> None:
    """ELIGIBLE and LIKELY_ELIGIBLE both wait.

    Not silence for its own sake: this customer is mid-journey, and the claim
    they are about to submit carries everything this would have carried.
    """
    sender = Recorder()
    claim = await a_claim(session, number)

    assert notify_ops_check(
        sender, claim.check, to="ops@example.com", base_url="http://x"
    ) is False
    assert sender.sent == []


async def test_an_undecided_check_is_still_reported(session: Session) -> None:
    """A check that never reached a verdict is a failure of ours, not an
    answer, and is treated like NEEDS_REVIEW.

    Staying quiet about it would mean a provider could break completely and
    the inbox would simply go calm -- which reads exactly like a quiet day.
    """
    sender = Recorder()
    claim = await a_claim(session, "XX999")
    assert claim.check.verdict is None

    assert notify_ops_check(
        sender, claim.check, to="ops@example.com", base_url="http://x"
    )
    assert len(sender.sent) == 1


async def test_a_claim_produces_exactly_one_email_end_to_end(
    session: Session,
) -> None:
    """THE test in this section.

    The whole journey of somebody who qualifies: they check, they are told
    yes, they fill the form in, they submit. The company hears about them once.

    Before this rule they were heard about twice -- a check email and a claim
    email, two rows in the inbox for one person, and no way for whoever works
    that inbox to tell that they were the same person.
    """
    sender = Recorder()
    claim = await a_claim(session, "LH687")

    # What the customer's journey actually triggers, in order.
    notify_ops_check(sender, claim.check, to="ops@example.com", base_url="http://x")
    submit_claim(session, claim)
    notify_ops_claim(sender, claim, to="ops@example.com", base_url="http://x")

    assert len(sender.sent) == 1, [m.subject for m in sender.sent]
    assert claim.contact_name in sender.sent[0].subject


async def test_two_identical_anonymous_checks_do_not_collide(
    session: Session,
) -> None:
    """A mail client threads on the subject, so an identical one HIDES a message.

    Two people checking the same flight on the same day is not hypothetical --
    it is what a cancellation looks like. It happened here within a minute of
    the feature going live: two checks of BZ734 collapsed into one row and the
    inbox showed three emails where four had been sent.

    The assertion is DISTINCTNESS rather than "the subject contains the
    reference", because distinctness is the property that keeps a message
    visible; how it is achieved is not the point.
    """
    sender = Recorder()
    first = await a_claim(session, "LY325")
    second = await a_claim(session, "LY325")
    for claim in (first, second):
        claim.check.contact_name = None
    session.flush()

    for claim in (first, second):
        notify_ops_check(sender, claim.check, to="ops@example.com", base_url="http://x")

    subjects = [message.subject for message in sender.sent]
    assert len(subjects) == 2
    assert subjects[0] != subjects[1], subjects


async def test_the_reference_in_the_subject_finds_the_row(session: Session) -> None:
    """The reference is a search key, not decoration.

    Somebody forwards an ops email and asks "which check was this?". Pasting
    the token into the admin API or the database has to answer that, which
    means it must be derived from the id rather than invented.
    """
    sender = Recorder()
    claim = await a_claim(session, "LY325")

    notify_ops_check(sender, claim.check, to="ops@example.com", base_url="http://x")

    reference = ops_reference(claim.check.id)
    assert reference in sender.sent[0].subject
    assert reference in sender.sent[0].text
    assert str(claim.check.id).replace("-", "").upper().startswith(reference)


# --- The same rule, over HTTP ------------------------------------------------
#
# The service-level tests above prove the decision. These prove the ROUTE asks
# for it -- that the rule is not sitting in a function nobody calls.


@pytest.fixture
def ops_client(app, settings: Settings) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    """A client whose settings name a company inbox, as a deployment does.

    Copied from the shared settings rather than built fresh, so the background
    task -- which opens its own engine from `database_url` -- reaches the same
    database the request wrote to. A second URL here produces "no such table",
    which is a fixture bug wearing the costume of a real one.
    """
    from app.api.deps import get_settings_dependency

    configured = settings.model_copy(update={"ops_email": "ops@example.com"})
    app.dependency_overrides[get_settings_dependency] = lambda: configured
    with TestClient(app) as test_client:
        create_all(app.state.engine)
        yield test_client


def test_over_http_a_qualifying_check_tells_the_company_nothing(
    ops_client: TestClient,
) -> None:
    """The customer is on their way to the claim form; one email will follow."""
    from app.api.deps import get_email_sender

    sender = Recorder()
    ops_client.app.dependency_overrides[get_email_sender] = lambda: sender  # type: ignore[attr-defined]

    response = ops_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": "2026-08-14"},
    )

    assert response.json()["verdict"] == "ELIGIBLE"
    assert sender.sent == [], [m.subject for m in sender.sent]


def test_over_http_a_rejection_reaches_the_company(ops_client: TestClient) -> None:
    """Their journey ends at the result screen, so this is their one email."""
    from app.api.deps import get_email_sender

    sender = Recorder()
    ops_client.app.dependency_overrides[get_email_sender] = lambda: sender  # type: ignore[attr-defined]

    response = ops_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "LY325", "flight_date": "2026-08-14"},
    )

    assert response.json()["verdict"] == "NOT_ELIGIBLE"
    assert len(sender.sent) == 1
    assert sender.sent[0].to == "ops@example.com"
    assert "LY325" in sender.sent[0].subject


# --- The documents that travel with a claim ----------------------------------
#
# "IMG_5992.jpg" in a list tells somebody chasing an airline nothing at all.
# The photograph of the receipt IS the evidence, and the person who has to act
# on it works from an inbox.
#
# It is also the only durable copy. Uploads live on the container's own disk,
# which on a managed host does not survive a deploy -- so a link would rot
# quietly while an attachment keeps working.


class _Storage:
    """In-memory FileStorage. Satisfies the protocol the notifier needs."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = files or {}

    def save(self, content: bytes, *, content_type: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def open(self, path: str) -> bytes:
        return self.files[path]

    def delete(self, path: str) -> None:
        self.files.pop(path, None)


def _attach_document(
    session: Session, claim, *, name="IMG_5992.jpg", kind="RECEIPT", size=2048
):  # type: ignore[no-untyped-def]
    from app.db.models import Document

    path = f"ab/cd/{name}"
    document = Document(
        claim_id=claim.id,
        kind=kind,
        original_filename=name,
        stored_path=path,
        content_type="image/jpeg",
        size_bytes=size,
    )
    session.add(document)
    session.flush()
    return path, b"\xff\xd8\xff" + b"x" * (size - 3)


async def test_an_uploaded_photo_is_attached(session: Session) -> None:
    """THE test in this section.

    A receipt named in a list is a receipt nobody can see. Somebody writing to
    an airline needs the picture, in the message, without opening the system.
    """
    sender = Recorder()
    claim = await a_claim(session)
    path, content = _attach_document(session, claim)

    notify_ops_claim(
        sender, claim, to="ops@example.com", base_url="http://x",
        storage=_Storage({path: content}),
    )

    attachments = sender.sent[0].attachments
    assert len(attachments) == 1
    assert attachments[0].filename == "IMG_5992.jpg"
    assert attachments[0].content == content
    assert attachments[0].content_type == "image/jpeg"


async def test_the_body_says_which_documents_are_attached(session: Session) -> None:
    """A list that silently omits one is worse than one that never promised it.

    Whoever is chasing the airline believes they are holding everything, and
    finds out they are not at the point where it costs something.
    """
    sender = Recorder()
    claim = await a_claim(session)
    path, content = _attach_document(session, claim)

    notify_ops_claim(
        sender, claim, to="ops@example.com", base_url="http://x",
        storage=_Storage({path: content}),
    )

    assert "attached" in sender.sent[0].text


async def test_a_file_that_cannot_be_read_does_not_lose_the_claim(
    session: Session,
) -> None:
    """Storage on a managed host does not survive a deploy.

    A claim submitted before one and emailed after it points at bytes that
    are gone. The claim details are the valuable part and must still arrive --
    losing the whole message over a missing photograph would be the expensive
    failure, not the cheap one.
    """
    sender = Recorder()
    claim = await a_claim(session)
    _attach_document(session, claim)  # stored_path deliberately not in storage

    assert notify_ops_claim(
        sender, claim, to="ops@example.com", base_url="http://x",
        storage=_Storage({}),
    )
    message = sender.sent[0]
    assert message.attachments == ()
    assert claim.reference in message.text
    assert "in the system" in message.text


async def test_identity_documents_never_travel(session: Session) -> None:
    """A photograph of a passport is strictly worse than the number on it.

    Identity numbers are kept out of the inbox deliberately -- encrypted at
    rest for a reason, and an inbox is unencrypted, forwarded, backed up by a
    mail provider and searchable forever. The same rule has to cover a scan.

    Nothing uploads this kind today. The rule is here so that the day somebody
    adds "upload your passport", the safe behaviour is already the default.
    """
    sender = Recorder()
    claim = await a_claim(session)
    path, content = _attach_document(
        session, claim, name="passport.jpg", kind="IDENTIFICATION"
    )

    notify_ops_claim(
        sender, claim, to="ops@example.com", base_url="http://x",
        storage=_Storage({path: content}),
    )

    message = sender.sent[0]
    assert message.attachments == ()
    # Still ACKNOWLEDGED, so nobody thinks it was never uploaded.
    assert "passport.jpg" in message.text


async def test_the_total_size_is_capped(session: Session) -> None:
    """An email refused for size is an email that silently does not arrive.

    Each upload may be 10MB and a claim may have several, which is more than
    a provider will take. Budgeted against the BASE64 size, because that is
    what goes over the wire.
    """
    from app.services.notifications import MAX_ATTACHED_BYTES

    sender = Recorder()
    claim = await a_claim(session)
    files = {}
    for i in range(4):
        path, content = _attach_document(
            session, claim, name=f"big{i}.jpg", size=6 * 1024 * 1024
        )
        files[path] = content

    notify_ops_claim(
        sender, claim, to="ops@example.com", base_url="http://x",
        storage=_Storage(files),
    )

    message = sender.sent[0]
    encoded = sum(-(-a.size_bytes * 4 // 3) for a in message.attachments)
    assert encoded <= MAX_ATTACHED_BYTES
    assert len(message.attachments) < 4, "some had to be left behind"
    assert "in the system" in message.text, "and the body must say so"


async def test_no_storage_still_sends_the_claim(session: Session) -> None:
    """The details are the valuable part and must not depend on the files."""
    sender = Recorder()
    claim = await a_claim(session)
    _attach_document(session, claim)

    assert notify_ops_claim(
        sender, claim, to="ops@example.com", base_url="http://x",
    )
    assert sender.sent[0].attachments == ()
