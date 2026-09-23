"""Tests for the eligibility endpoint.

Against a real application, a real database and the fake provider -- no
patching. These test the wiring and the contract, not the law: whether a flight
is owed 520 pounds was settled in test_uk261.py, and repeating it here would
mean two places to update when a rule changes.
"""

import pytest
from fastapi.testclient import TestClient

AUG_14 = "2026-08-14"


def post(client: TestClient, **payload: object) -> tuple[int, dict]:  # type: ignore[type-arg]
    response = client.post("/api/v1/eligibility/check", json=payload)
    return response.status_code, response.json()


# --- The happy path ----------------------------------------------------------


def test_a_delayed_flight_returns_a_verdict_and_an_amount(
    client: TestClient,
) -> None:
    code, body = post(client, flight_number="BA165", flight_date=AUG_14)

    assert code == 200
    assert body["status"] == "DECIDED"
    assert body["verdict"] == "ELIGIBLE"
    assert body["best_regulation"] == "UK261"
    assert body["best_award"] == {
        "amount": "520.00", "currency": "GBP", "formatted": "£520.00"
    }


def test_the_amount_is_a_string_not_a_json_number(client: TestClient) -> None:
    """JSON numbers are IEEE doubles in most parsers.

    A payout that arrives in the browser as 519.99999999 is the same bug Money
    exists to prevent, one layer further out. The response carries an exact
    decimal string and a preformatted display value, so no client ever has to
    do currency arithmetic in floating point.
    """
    _, body = post(client, flight_number="BA165", flight_date=AUG_14)
    assert isinstance(body["best_award"]["amount"], str)


def test_all_three_regulations_are_returned_with_reasons(
    client: TestClient,
) -> None:
    """An unexplained "no" destroys trust.

    A customer who can see that two laws did not cover them and the third had a
    higher threshold understands the answer instead of doubting it.
    """
    _, body = post(client, flight_number="BA165", flight_date=AUG_14)

    assert {o["regulation"] for o in body["outcomes"]} == {"EC261", "UK261", "ISRAEL"}
    assert all(o["reason"] for o in body["outcomes"])

    israel = next(o for o in body["outcomes"] if o["regulation"] == "ISRAEL")
    assert israel["applies"] is True  # covered, but below the 8-hour threshold
    ec261 = next(o for o in body["outcomes"] if o["regulation"] == "EC261")
    assert ec261["applies"] is False  # not covered at all


def test_the_flight_is_echoed_back(client: TestClient) -> None:
    """So the customer can confirm we looked up the right flight before
    building a claim on it."""
    _, body = post(client, flight_number="BA165", flight_date=AUG_14)

    flight = body["flight"]
    assert flight["route"] == "TLV → LHR"
    assert flight["arrival_delay_hours"] == 4.0
    assert flight["distance_km"] == 3588.6


def test_the_caveat_rides_along_with_a_claim(client: TestClient) -> None:
    """No flight database records why a flight was late, and weather excuses
    the airline entirely."""
    _, body = post(client, flight_number="BA165", flight_date=AUG_14)
    assert "extraordinary" in body["caveat"]


def test_a_flight_owed_by_two_laws_shows_both(client: TestClient) -> None:
    _, body = post(client, flight_number="BA165", flight_date="2026-08-20")
    eligible = [o for o in body["outcomes"] if o["verdict"] == "ELIGIBLE"]
    assert len(eligible) == 2


def test_a_confident_no_is_still_returned(client: TestClient) -> None:
    """The system has to be willing to say no, or the product is useless."""
    _, body = post(client, flight_number="LY325", flight_date=AUG_14)
    assert body["verdict"] == "NOT_ELIGIBLE"
    assert body["best_award"] is None
    assert len(body["outcomes"]) == 3


# --- Why everything is 200 ---------------------------------------------------


def test_a_flight_that_does_not_exist_is_200_not_404(client: TestClient) -> None:
    """The endpoint worked, the lookup happened, and a record was stored.

    A 404 would tell a client the endpoint does not exist, and many HTTP
    libraries discard the body on an error status -- throwing away the message
    that explains the date should be the departure date, which is the actual
    cause nine times out of ten.
    """
    code, body = post(client, flight_number="XX999", flight_date=AUG_14)

    assert code == 200
    assert body["status"] == "NOT_FOUND"
    assert body["verdict"] is None
    assert "check the flight number" in body["message"]


def test_a_provider_outage_is_needs_review_never_a_denial(
    client: TestClient,
) -> None:
    """The most expensive bug this system could have.

    Someone who reads "no claim" and closes the tab has lost money nobody will
    ever know about. An outage is not evidence about anybody's flight.
    """
    code, body = post(client, flight_number="ERR503", flight_date=AUG_14)

    assert code == 200
    assert body["status"] == "UNRESOLVED"
    assert body["verdict"] == "NEEDS_REVIEW"
    assert "do not assume you have no claim" in body["message"]


def test_the_outage_message_never_leaks_internals(client: TestClient) -> None:
    """Vendor names and status codes help nobody outside the building."""
    _, body = post(client, flight_number="ERR401", flight_date=AUG_14)
    for leak in ("aerodatabox", "ProviderAuthError", "401", "ERR401"):
        assert leak not in body["message"]


def test_a_gap_in_our_reference_data_is_reported_as_ours(
    client: TestClient,
) -> None:
    _, body = post(client, flight_number="ZZ999", flight_date=AUG_14)
    assert body["verdict"] == "NEEDS_REVIEW"
    assert "We could not fully identify" in body["message"]


# --- Several matching flights ------------------------------------------------


def test_two_matching_flights_ask_which_one(client: TestClient) -> None:
    """FR1234 flew Dublin to Stansted twice that day, 11 minutes late and
    4h 35m late. Guessing would tell half those passengers a confident answer
    about a journey they did not take."""
    code, body = post(client, flight_number="FR1234", flight_date=AUG_14)

    assert code == 200
    assert body["status"] == "AMBIGUOUS"
    assert body["verdict"] is None
    assert len(body["options"]) == 2
    assert all("DUB → STN" in o["label"] for o in body["options"])


def test_choosing_an_option_resolves_the_check(client: TestClient) -> None:
    _, ambiguous = post(client, flight_number="FR1234", flight_date=AUG_14)

    verdicts = set()
    for option in ambiguous["options"]:
        _, resolved = post(
            client, flight_number="FR1234", flight_date=AUG_14,
            option_key=option["key"],
        )
        assert resolved["status"] == "DECIDED"
        verdicts.add(resolved["verdict"])

    assert verdicts == {"ELIGIBLE", "NOT_ELIGIBLE"}


# --- Input validation --------------------------------------------------------


def test_flight_numbers_are_normalised_before_any_lookup(
    client: TestClient,
) -> None:
    """Customers type "ba 165", "BA-165" and "ba165". None should cost an API
    call to discover they are the same flight."""
    for typed in ("ba 165", "BA-165", " ba165 "):
        _, body = post(client, flight_number=typed, flight_date=AUG_14)
        assert body["verdict"] == "ELIGIBLE", typed


@pytest.mark.parametrize(
    "bad", ["", "X", "12345678", "BA", "!!!", "FLIGHT165"]
)
def test_a_malformed_flight_number_is_422(client: TestClient, bad: str) -> None:
    """A malformed request IS an HTTP error, unlike a flight that does not
    exist. Nothing was looked up and nothing was stored."""
    code, _ = post(client, flight_number=bad, flight_date=AUG_14)
    assert code == 422


def test_a_future_date_is_rejected_with_a_useful_message(
    client: TestClient,
) -> None:
    """The commonest user error: entering the return date, or next year.

    Catching it here says so, instead of spending a lookup to report "flight
    not found" -- which sends the customer hunting for a typo in the number.
    """
    code, body = post(client, flight_number="BA165", flight_date="2099-01-01")
    assert code == 422
    assert "בעתיד" in str(body["detail"])


def test_a_flight_older_than_every_limitation_period_is_rejected(
    client: TestClient,
) -> None:
    """Six years is the longest anywhere we cover. Beyond it there is nothing
    to claim, and asking the provider would spend money to say so."""
    code, body = post(client, flight_number="BA165", flight_date="2000-01-01")
    assert code == 422
    assert "שש שנים" in str(body["detail"])


def test_a_malformed_email_is_rejected(client: TestClient) -> None:
    """The confirmation email is how a customer hears from us again."""
    code, _ = post(
        client, flight_number="BA165", flight_date=AUG_14, contact_email="not-an-email"
    )
    assert code == 422


def test_contact_details_are_optional(client: TestClient) -> None:
    """Demanding a name before answering would lose most visitors."""
    code, body = post(client, flight_number="BA165", flight_date=AUG_14)
    assert code == 200 and body["verdict"] == "ELIGIBLE"


# --- Persistence -------------------------------------------------------------


def test_every_check_is_stored_whatever_it_concluded(client: TestClient) -> None:
    """The failures are the most valuable rows: they are the review queue, and
    they are how anyone notices a provider has started quietly failing."""
    from app.db.models import EligibilityCheck

    for number in ("BA165", "LY325", "XX999", "ERR503", "FR1234"):
        post(client, flight_number=number, flight_date=AUG_14)

    from app.db.session import create_session_factory

    factory = create_session_factory(client.app.state.engine)  # type: ignore[attr-defined]
    with factory() as session:
        assert session.query(EligibilityCheck).count() == 5


def test_contact_details_are_stored_with_the_check(client: TestClient) -> None:
    from app.db.models import EligibilityCheck
    from app.db.session import create_session_factory

    post(
        client, flight_number="BA165", flight_date=AUG_14,
        contact_name="Noam Hasson", contact_email="Noam@Example.COM",
    )

    factory = create_session_factory(client.app.state.engine)  # type: ignore[attr-defined]
    with factory() as session:
        row = session.query(EligibilityCheck).one()
        assert row.contact_name == "Noam Hasson"
        assert row.contact_email == "noam@example.com"


def test_a_check_can_be_read_back_by_id(client: TestClient) -> None:
    """The claim form quotes this id, so it has to resolve later."""
    _, created = post(client, flight_number="BA165", flight_date=AUG_14)

    response = client.get(f"/api/v1/eligibility/checks/{created['check_id']}")
    assert response.status_code == 200

    stored = response.json()
    assert stored["verdict"] == "ELIGIBLE"
    assert stored["best_award"]["formatted"] == "£520.00"
    assert len(stored["outcomes"]) == 3
    assert stored["flight"]["route"] == "TLV → LHR"


def test_reading_a_check_does_not_ask_the_provider_again(
    client: TestClient,
) -> None:
    """The answer must be the one the customer was actually given.

    A fresh lookup could now say something different -- data gets corrected --
    and showing them a new verdict for the same check would be indefensible.
    """
    _, created = post(client, flight_number="BA165", flight_date=AUG_14)

    first = client.get(f"/api/v1/eligibility/checks/{created['check_id']}").json()
    second = client.get(f"/api/v1/eligibility/checks/{created['check_id']}").json()
    assert first == second


def test_an_unknown_check_id_is_404(client: TestClient) -> None:
    """Here a 404 IS right: the resource genuinely does not exist."""
    response = client.get(
        "/api/v1/eligibility/checks/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# --- The contract ------------------------------------------------------------


def test_the_endpoint_is_documented(client: TestClient) -> None:
    """The OpenAPI document is what the frontend gets written against, and it
    is generated from the same models the server validates with."""
    document = client.get("/openapi.json").json()
    assert "/api/v1/eligibility/check" in document["paths"]
    assert "post" in document["paths"]["/api/v1/eligibility/check"]

