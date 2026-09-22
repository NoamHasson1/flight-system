"""Tests for the email layer.

The theme throughout: **a failed email must never fail the thing it was
reporting on**. A customer who submits a claim and sees an error because our
mail server is down will assume the claim did not go through, and will either
give up or submit it twice. The claim is the valuable thing; the email is a
courtesy.
"""

import json
import smtplib
from unittest.mock import patch

import httpx
import pytest

from app.email.resend import ResendEmailSender
from app.email.base import EmailError, EmailMessage, EmailSender
from app.email.console import ConsoleEmailSender
from app.email.messages import check_result, claim_submitted
from app.email.registry import AVAILABLE, build_email_sender
from app.email.smtp import SmtpEmailSender


def a_message(**overrides: object) -> EmailMessage:
    base: dict[str, object] = {
        "to": "noam@example.com",
        "subject": "Your claim is with us",
        "text": "plain",
        "html": "<p>rich</p>",
    }
    base.update(overrides)
    return EmailMessage(**base)  # type: ignore[arg-type]


# --- The message ------------------------------------------------------------


def test_both_bodies_are_required() -> None:
    """A plain-text part is not a legacy courtesy.

    It is what spam filters score, what screen readers prefer, and what renders
    when a client blocks HTML. Optional means skipped, and then the mail lands
    in spam for a reason nobody can find.
    """
    with pytest.raises(ValueError, match="both a text and an HTML body"):
        a_message(text="")
    with pytest.raises(ValueError, match="both a text and an HTML body"):
        a_message(html="")


@pytest.mark.parametrize("address", ["", "   ", "not-an-address"])
def test_a_bad_address_is_refused(address: str) -> None:
    with pytest.raises(ValueError, match="not an email address"):
        a_message(to=address)


def test_a_message_needs_a_subject() -> None:
    with pytest.raises(ValueError, match="needs a subject"):
        a_message(subject="  ")


# --- The console sender -----------------------------------------------------


def test_the_console_sender_satisfies_the_contract() -> None:
    """The same assertion made against SMTP: both adapters are interchangeable,
    which is what lets everything above them be tested without a mail server."""
    assert isinstance(ConsoleEmailSender(), EmailSender)


def test_the_console_sender_logs_the_whole_body(caplog: pytest.LogCaptureFixture) -> None:
    """Reviewable, not merely counted.

    The point of the console sender is that somebody can read what would have
    been sent. A log line saying "1 email" proves nothing about the copy.
    """
    with caplog.at_level("INFO", logger="flight_system.email"):
        assert ConsoleEmailSender().send(a_message(text="Reference FS-2026-K7M9QX"))
    assert "FS-2026-K7M9QX" in caplog.text
    assert "noam@example.com" in caplog.text


# --- SMTP -------------------------------------------------------------------


def test_smtp_without_a_host_fails_at_construction() -> None:
    """Not at send time.

    A missing host is a deployment mistake, and finding it when the process
    starts is far cheaper than finding it in a log after a customer did not get
    their confirmation.
    """
    with pytest.raises(EmailError, match="SMTP_HOST is not set"):
        SmtpEmailSender(host="", port=587, sender="a@b.com")


def test_smtp_without_a_from_address_fails_at_construction() -> None:
    with pytest.raises(EmailError, match="EMAIL_FROM is not set"):
        SmtpEmailSender(host="smtp.example.com", port=587, sender="")


def test_a_refused_connection_returns_false_rather_than_raising() -> None:
    """The single most important test in this file.

    The caller is never in a position to act on an exception: the claim is
    already stored and the customer is already looking at their reference.
    Raising here would turn a working submission into a 500.
    """
    sender = SmtpEmailSender(host="smtp.example.com", port=587, sender="a@b.com")
    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        assert sender.send(a_message()) is False


def test_an_smtp_error_returns_false_too() -> None:
    sender = SmtpEmailSender(host="smtp.example.com", port=587, sender="a@b.com")
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPAuthenticationError(535, b"no")):
        assert sender.send(a_message()) is False


def test_a_failure_is_logged_with_the_recipient(caplog: pytest.LogCaptureFixture) -> None:
    """Silently swallowed is not the same as silently ignored. Somebody has to
    be able to find out who did not get their email."""
    sender = SmtpEmailSender(host="smtp.example.com", port=587, sender="a@b.com")
    with caplog.at_level("ERROR", logger="flight_system.email"):
        with patch("smtplib.SMTP", side_effect=OSError("boom")):
            sender.send(a_message(to="dana@example.com"))
    assert "dana@example.com" in caplog.text


# --- The registry -----------------------------------------------------------


def test_the_registry_lists_every_sender() -> None:
    assert AVAILABLE == ("console", "smtp", "resend")


def test_an_unknown_sender_raises_value_error() -> None:
    """A misconfigured sender is a deployment mistake that should stop the
    application at startup, not turn into silently unsent mail."""
    with pytest.raises(ValueError, match="unknown email sender"):
        build_email_sender("postmark-sdk", object())


# --- The messages themselves ------------------------------------------------


def a_claim_email(**overrides: object) -> EmailMessage:
    base: dict[str, object] = {
        "to": "noam@example.com",
        "contact_name": "Noam",
        "reference": "FS-2026-K7M9QX",
        "flight_number": "BA165",
        "route": "TLV → LHR",
        "amount": "£520.00",
        "passenger_count": 1,
        "claim_url": "https://example.com/claim/1",
    }
    base.update(overrides)
    return claim_submitted(**base)  # type: ignore[arg-type]


def test_the_subject_carries_the_information() -> None:
    """Many people never open the mail.

    They read the subject in a list and act on it. "Your claim FS-2026-K7M9QX
    is with us" tells them what happened; "Thanks for your submission" tells
    them nothing and gets archived.
    """
    assert a_claim_email().subject == "Your claim FS-2026-K7M9QX is with us"


def test_nothing_important_lives_only_in_the_html() -> None:
    """A client that blocks HTML must not leave somebody holding an empty
    email about their money."""
    message = a_claim_email()
    for essential in ("FS-2026-K7M9QX", "BA165", "£520.00", "TLV → LHR"):
        assert essential in message.text, essential
        assert essential in message.html, essential


def test_the_amount_says_how_many_passengers_it_covers() -> None:
    """Compensation is per passenger, so "£520" alone understates a family's
    claim by a factor of four."""
    assert "for 4 passengers" in a_claim_email(passenger_count=4).text
    assert "for 1 passengers" not in a_claim_email(passenger_count=1).text


def test_a_claim_email_survives_a_missing_amount() -> None:
    """A NEEDS_REVIEW check can become a claim with no figure attached."""
    message = a_claim_email(amount=None)
    assert "your compensation" in message.text


@pytest.mark.parametrize(
    ("verdict", "amount", "expected"),
    [
        ("ELIGIBLE", "£520.00", "you can claim £520.00"),
        ("NEEDS_REVIEW", None, "check this by hand"),
        ("NOT_ELIGIBLE", None, "doesn't qualify"),
    ],
)
def test_the_result_subject_states_the_outcome(
    verdict: str, amount: str | None, expected: str
) -> None:
    message = check_result(
        to="noam@example.com", flight_number="BA165", route="TLV → LHR",
        verdict=verdict, amount=amount, check_url="https://example.com/check/1",
    )
    assert expected in message.subject


def test_a_review_email_says_it_is_not_a_no() -> None:
    """The alternative reading costs the customer money."""
    message = check_result(
        to="noam@example.com", flight_number="LH687", route="TLV → FRA",
        verdict="NEEDS_REVIEW", amount=None, check_url="https://example.com/check/1",
    )
    assert "not a no" in message.text.lower()


def test_a_no_does_not_blame_the_reader() -> None:
    message = check_result(
        to="noam@example.com", flight_number="LY325", route="TLV → CDG",
        verdict="NOT_ELIGIBLE", amount=None, check_url="https://example.com/check/1",
    )
    assert "down to anything you did" in message.text


def test_the_link_is_in_the_text_part() -> None:
    """A URL only in an <a href> is a URL a plain-text reader cannot follow."""
    assert "https://example.com/check/1" in check_result(
        to="n@example.com", flight_number="BA165", route="TLV → LHR",
        verdict="ELIGIBLE", amount="£520.00",
        check_url="https://example.com/check/1",
    ).text


def test_the_html_is_a_complete_document() -> None:
    """Email clients are twenty years behind browsers: no stylesheets, no
    flexbox, and Outlook renders through Word. A 600px centred table with
    inline styles is the thing that works everywhere."""
    html = a_claim_email().html
    assert html.startswith("<!doctype html>")
    assert "<style>" not in html  # stripped by most clients
    assert 'role="presentation"' in html  # tables are layout, not data


# --- Resend, for hosts that close the SMTP ports -----------------------------


def test_resend_sends_over_https() -> None:
    """The reason this adapter exists.

    Render, Fly and most managed hosts shut ports 25, 465 and 587 -- a rented
    container that can open an SMTP connection is a spam relay waiting to be
    found. The symptom is exact and unhelpful: "[Errno 101] Network is
    unreachable", with correct credentials and correct settings.

    Port 443 is open.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "re_123"})

    sender = ResendEmailSender(
        "re_test_key", "Skyclaim <ops@example.com>",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert sender.send(_message()) is True

    request = seen[0]
    assert str(request.url).startswith("https://")
    assert request.headers["Authorization"] == "Bearer re_test_key"
    body = json.loads(request.content)
    assert body["to"] == ["noam@example.com"]
    assert body["text"] and body["html"], "both parts, or it scores as spam"


def test_resend_reports_a_refusal_in_the_provider_s_own_words() -> None:
    """The two refusals that actually happen -- an unverified sending domain,
    and a free account that may only write to its owner -- are explained
    clearly by Resend and not at all by a status code.

    Swallowing that makes "why did that one customer not get their
    confirmation" unanswerable.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "You can only send testing emails to your own "
                             "email address"},
        )

    sender = ResendEmailSender(
        "re_test_key", "onboarding@resend.dev",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert sender.send(_message()) is False


def test_resend_never_raises() -> None:
    """A failed email must not fail the thing it reported on. Somebody who
    files a claim and sees an error assumes it did not go through."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    sender = ResendEmailSender(
        "re_test_key", "ops@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert sender.send(_message()) is False


def test_resend_refuses_to_be_built_without_a_key() -> None:
    """At construction, not at the first send: a missing key that only
    surfaces when somebody files a claim is one nobody notices until it has
    already cost something."""
    with pytest.raises(ValueError, match="no API key"):
        ResendEmailSender("", "ops@example.com")


def _message() -> EmailMessage:
    return EmailMessage(
        to="noam@example.com",
        subject="[Skyclaim] Noam Hasson · ELIGIBLE",
        text="plain",
        html="<p>rich</p>",
    )
