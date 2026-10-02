"""Tests for the admin API.

Half of these are about the guard, and that is the right proportion: this
endpoint lists every customer's name, email address and the reasoning behind
every verdict. Getting the data right matters less than making sure the wrong
person cannot read it.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_settings_dependency
from app.config import Settings
from app.db.session import create_all
from app.main import create_app

KEY = "test-admin-key-do-not-use-anywhere-real"
AUTH = {"X-Admin-Key": KEY}
AUG_14 = "2026-08-14"


@pytest.fixture
def admin_settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'admin.db'}",
        upload_dir=tmp_path / "uploads",
        flight_provider="fake",
        admin_api_key=KEY,
    )


@pytest.fixture
def admin_client(admin_settings: Settings):  # type: ignore[no-untyped-def]
    app: FastAPI = create_app(admin_settings)
    with TestClient(app) as client:
        create_all(app.state.engine)
        yield client


def seed(client: TestClient) -> None:
    """A realistic morning: some eligible, some not, some broken."""
    for number in ("BA165", "BA165", "LY325", "LH687", "ERR503", "XX999"):
        client.post(
            "/api/v1/eligibility/check",
            json={
                "flight_number": number, "flight_date": AUG_14,
                "contact_name": "Noam Hasson", "contact_email": "noam@example.com",
            },
        )


# --- The guard ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/summary",
        "/api/v1/admin/checks",
        "/api/v1/admin/claims",
        "/api/v1/admin/customers",
        "/api/v1/admin/flights",
    ],
)
def test_every_admin_route_requires_a_key(
    admin_client: TestClient, path: str
) -> None:
    """The guard is on the router, not on each route.

    One line, and it cannot be forgotten on the next endpoint somebody adds --
    which is exactly how admin endpoints end up unprotected.
    """
    assert admin_client.get(path).status_code == 401
    assert admin_client.get(path, headers=AUTH).status_code == 200


def test_a_wrong_key_is_refused(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/v1/admin/checks", headers={"X-Admin-Key": "wrong"}
    )
    assert response.status_code == 401


def test_a_wrong_key_and_a_missing_key_look_identical(
    admin_client: TestClient,
) -> None:
    """So probing cannot distinguish "there is no admin API here" from "you
    guessed wrong"."""
    missing = admin_client.get("/api/v1/admin/checks")
    wrong = admin_client.get("/api/v1/admin/checks", headers={"X-Admin-Key": "x"})
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


def test_with_no_key_configured_the_admin_api_is_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Fails CLOSED, not open.

    The alternative ships an unprotected list of every customer's name, email
    and national identity number because somebody forgot an environment
    variable. 503 says the API is not configured here, which is true and gives
    an attacker nothing.
    """
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'x.db'}",
        admin_api_key="",
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings_dependency] = lambda: settings

    with TestClient(app) as client:
        for headers in ({}, {"X-Admin-Key": "anything"}):
            response = client.get("/api/v1/admin/checks", headers=headers)
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]


def test_the_key_is_never_echoed_back(admin_client: TestClient) -> None:
    for headers in (AUTH, {"X-Admin-Key": "wrong-guess"}):
        response = admin_client.get("/api/v1/admin/checks", headers=headers)
        assert KEY not in response.text
        assert "wrong-guess" not in response.text


def test_the_customer_endpoints_are_still_open(admin_client: TestClient) -> None:
    """The guard must not leak onto the public routes."""
    response = admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    )
    assert response.status_code == 200


# --- The review queue --------------------------------------------------------


def test_the_review_queue_is_the_query_this_exists_for(
    admin_client: TestClient,
) -> None:
    """Everything the system could not decide, which a person must work rather
    than let quietly become a no."""
    seed(admin_client)

    response = admin_client.get(
        "/api/v1/admin/checks", params={"verdict": "NEEDS_REVIEW"}, headers=AUTH
    )
    body = response.json()

    # The provider outage. NOT the cancellation, which is priced and waiting on
    # the passenger rather than on anyone here.
    assert body["total"] == 1
    assert all(item["verdict"] == "NEEDS_REVIEW" for item in body["items"])


def test_every_queued_row_says_what_to_do_about_it(
    admin_client: TestClient,
) -> None:
    """A review queue nobody can skim is a review queue nobody works."""
    seed(admin_client)

    body = admin_client.get(
        "/api/v1/admin/checks", params={"verdict": "NEEDS_REVIEW"}, headers=AUTH
    ).json()
    assert all(item["message"] for item in body["items"])


def test_checks_can_be_filtered_by_flight(admin_client: TestClient) -> None:
    seed(admin_client)

    body = admin_client.get(
        "/api/v1/admin/checks",
        params={"flight_number": "ba165", "flight_date": AUG_14},
        headers=AUTH,
    ).json()
    assert body["total"] == 2


def test_listing_is_paginated_with_a_real_total(admin_client: TestClient) -> None:
    """The total is what makes a list usable.

    Without it nobody can tell whether "50 results" means fifty or the first
    fifty of nine thousand.
    """
    seed(admin_client)

    body = admin_client.get(
        "/api/v1/admin/checks", params={"limit": 2, "offset": 0}, headers=AUTH
    ).json()
    assert len(body["items"]) == 2
    assert body["total"] == 6


def test_the_total_matches_the_filter(admin_client: TestClient) -> None:
    """The listing and the count share one filter builder.

    Computed separately they drift, and a page whose total came from different
    criteria is a paginator that lies.
    """
    seed(admin_client)

    body = admin_client.get(
        "/api/v1/admin/checks",
        params={"verdict": "ELIGIBLE", "limit": 1},
        headers=AUTH,
    ).json()
    assert len(body["items"]) == 1
    assert body["total"] == 2


def test_the_page_size_is_capped(admin_client: TestClient) -> None:
    """Without a ceiling, ?limit=1000000 is a denial of service anybody can
    perform with a browser."""
    response = admin_client.get(
        "/api/v1/admin/checks", params={"limit": 100000}, headers=AUTH
    )
    assert response.status_code == 422


# --- Opening one check -------------------------------------------------------


def test_a_check_opens_with_its_full_evidence(admin_client: TestClient) -> None:
    """The flight snapshot, all three regulations' reasoning, and the untouched
    provider payload -- which is what lets a disputed verdict be re-explained
    months later."""
    created = admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    ).json()

    body = admin_client.get(
        f"/api/v1/admin/checks/{created['check_id']}", headers=AUTH
    ).json()

    assert body["flight_snapshot"]["origin_iata"] == "TLV"
    assert len(body["result_detail"]["outcomes"]) == 3
    assert body["provider_payload"] is not None


def test_other_passengers_on_the_same_flight_are_surfaced(
    admin_client: TestClient,
) -> None:
    """They belong in one claim: cheaper to run and far stronger against the
    airline than the same facts argued five times."""
    first = admin_client.post(
        "/api/v1/eligibility/check",
        json={
            "flight_number": "BA165", "flight_date": AUG_14,
            "contact_email": "noam@example.com",
        },
    ).json()
    admin_client.post(
        "/api/v1/eligibility/check",
        json={
            "flight_number": "BA165", "flight_date": AUG_14,
            "contact_email": "dana@example.com",
        },
    )

    body = admin_client.get(
        f"/api/v1/admin/checks/{first['check_id']}", headers=AUTH
    ).json()

    assert len(body["others_on_this_flight"]) == 1
    assert body["others_on_this_flight"][0]["contact_email"] == "dana@example.com"


def test_a_row_says_whether_it_already_became_a_claim(
    admin_client: TestClient,
) -> None:
    """The conversion question, answered per row: who was told yes and did
    nothing about it."""
    created = admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    ).json()

    before = admin_client.get("/api/v1/admin/checks", headers=AUTH).json()
    assert before["items"][0]["has_claim"] is False

    admin_client.post(
        "/api/v1/claims",
        json={
            "check_id": created["check_id"], "contact_name": "Noam",
            "contact_email": "noam@example.com",
            "passengers": [{"full_name": "Noam Hasson"}],
        },
    )

    after = admin_client.get("/api/v1/admin/checks", headers=AUTH).json()
    assert after["items"][0]["has_claim"] is True


def test_an_unknown_check_is_404(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/v1/admin/checks/00000000-0000-0000-0000-000000000000", headers=AUTH
    )
    assert response.status_code == 404


# --- Claims ------------------------------------------------------------------


def test_claims_list_carries_the_flight_and_the_verdict(
    admin_client: TestClient,
) -> None:
    """So an operator can work the list without opening every row."""
    check = admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    ).json()
    admin_client.post(
        "/api/v1/claims",
        json={
            "check_id": check["check_id"], "contact_name": "Noam Hasson",
            "contact_email": "noam@example.com",
            "passengers": [{"full_name": "Noam Hasson"}, {"full_name": "Dana Hasson"}],
            "expenses": [
                {"category": "HOTEL", "amount": "180.00", "currency": "EUR"},
                {"category": "TRANSPORT", "amount": "240.50", "currency": "ILS"},
            ],
        },
    )

    row = admin_client.get("/api/v1/admin/claims", headers=AUTH).json()["items"][0]
    assert row["flight_number"] == "BA165"
    assert row["verdict"] == "ELIGIBLE"
    assert row["best_amount"] == "520.00"
    assert row["passenger_count"] == 2
    assert row["expense_totals"] == {"EUR": "180.00", "ILS": "240.50"}


# --- The summary -------------------------------------------------------------


def test_the_summary_counts_the_morning(admin_client: TestClient) -> None:
    seed(admin_client)

    body = admin_client.get("/api/v1/admin/summary", headers=AUTH).json()

    assert body["checks_total"] == 6
    assert body["checks_by_verdict"] == {
        "ELIGIBLE": 2,
        "LIKELY_ELIGIBLE": 1,
        "NOT_ELIGIBLE": 1,
        "NEEDS_REVIEW": 1,
    }
    assert body["needs_review"] == 1
    assert body["claims_total"] == 0


def test_pipeline_value_is_never_one_number(admin_client: TestClient) -> None:
    """Euro, pounds and shekels do not add up.

    A single "pipeline value" would be a figure nobody could defend, computed
    from an exchange rate nobody chose.
    """
    for number in ("BA165", "BA165", "LY324"):
        admin_client.post(
            "/api/v1/eligibility/check",
            json={"flight_number": number, "flight_date": AUG_14},
        )

    body = admin_client.get("/api/v1/admin/summary", headers=AUTH).json()
    assert body["eligible_value_by_currency"] == {"EUR": "400.00", "GBP": "1040.00"}


# --- The CRM -----------------------------------------------------------------
#
# The operator's screen. Its whole purpose is that nobody falls through, so
# most of these are about who APPEARS rather than about formatting.


import io  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _customer(client: TestClient, number: str = "BA165", **extra: object) -> str:
    """One check with contact details. Returns its id."""
    payload: dict[str, object] = {
        "flight_number": number,
        "flight_date": AUG_14,
        "contact_name": "Noam Hasson",
        "contact_email": "noam@example.com",
    }
    payload.update(extra)
    response = client.post("/api/v1/eligibility/check", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["check_id"]


def _claim_for(client: TestClient, check_id: str, **extra: object) -> dict:  # type: ignore[type-arg]
    payload: dict[str, object] = {
        "check_id": check_id,
        "contact_name": "נועם חסון",
        "contact_email": "noam@example.com",
        "contact_phone": "050-1234567",
        "passengers": [{"full_name": "נועם חסון", "national_id": "012345678"}],
    }
    payload.update(extra)
    response = client.post("/api/v1/claims", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_customer_who_was_refused_still_appears(admin_client: TestClient) -> None:
    """THE most important test on this screen.

    The list joins checks to claims, and the join must be an OUTER one. An
    inner join would quietly show only the people who filed -- and those are
    the minority. Everybody who was told no would vanish from the operator's
    world, which is precisely the group worth revisiting when a rule changes
    or a flight is re-derived.

    If this fails, the CRM looks like it is working and is hiding most of
    the customers.
    """
    _customer(admin_client, "XX999")  # a flight the fake provider cannot find

    body = admin_client.get("/api/v1/admin/customers", headers=AUTH).json()

    assert body["total"] == 1
    assert body["items"][0]["claim_id"] is None
    assert body["items"][0]["contact_email"] == "noam@example.com"


def test_somebody_who_left_no_details_is_not_in_the_list(
    admin_client: TestClient,
) -> None:
    """A flight number typed by a passer-by is not a customer.

    There is nobody to contact and nothing to follow up. Thousands of these
    arrive, and putting them in the list would bury the people who did leave
    an address -- so the default is off, and the flag exists because "how
    many looked and left" is a real question asked separately.
    """
    admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    )

    hidden = admin_client.get("/api/v1/admin/customers", headers=AUTH).json()
    shown = admin_client.get(
        "/api/v1/admin/customers?include_anonymous=true", headers=AUTH
    ).json()

    assert hidden["total"] == 0
    assert shown["total"] == 1


def test_the_claim_supplies_the_phone_number_and_the_better_name(
    admin_client: TestClient,
) -> None:
    """Two fields come from different rows, and the precedence matters.

    A phone number is only ever collected on the claim form -- a refused
    customer is never asked for one -- so for most rows it is correctly
    absent. The name exists in both places, and the claim's wins: it was
    typed to go on a letter to an airline, where the check's may be a first
    name typed in a hurry.
    """
    check_id = _customer(admin_client)
    _claim_for(admin_client, check_id)

    row = admin_client.get("/api/v1/admin/customers", headers=AUTH).json()["items"][0]

    assert row["contact_phone"] == "050-1234567"
    assert row["contact_name"] == "נועם חסון"
    assert row["claim_reference"].startswith("FS-")


def test_one_search_box_finds_a_person_by_whatever_the_operator_has(
    admin_client: TestClient,
) -> None:
    """An operator looking somebody up has ONE thing in hand.

    An email from a reply, a flight number from a phone call, a name. Making
    them pick which field it is first is a worse version of the same search,
    so one box covers all of them.
    """
    _customer(admin_client, "BA165", contact_email="first@example.com")
    _customer(admin_client, "LY325", contact_email="second@example.com")

    def found(q: str) -> int:
        return admin_client.get(
            f"/api/v1/admin/customers?search={q}", headers=AUTH
        ).json()["total"]

    assert found("second@") == 1
    assert found("LY325") == 1
    assert found("Noam") == 2, "both share a name"
    assert found("nobody-at-all") == 0


def test_the_total_counts_everyone_not_just_this_page(
    admin_client: TestClient,
) -> None:
    """Without this the screen says "50" when it means "the first 50".

    On a list whose entire purpose is that nobody is missed, the count of
    what matched is the number that matters most -- it is how an operator
    knows whether they have reached the end.
    """
    for i in range(5):
        _customer(admin_client, "BA165", contact_email=f"p{i}@example.com")

    body = admin_client.get("/api/v1/admin/customers?limit=2", headers=AUTH).json()

    assert len(body["items"]) == 2
    assert body["total"] == 5


def test_the_detail_screen_works_for_somebody_who_never_filed(
    admin_client: TestClient,
) -> None:
    """Keyed on the check, not the claim.

    Keying on the claim would make the detail button work for the people who
    got through and 404 for everybody who was refused -- the majority. They
    have no passengers and no receipts, and that is an empty section rather
    than an error.
    """
    check_id = _customer(admin_client, "XX999")

    response = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passengers"] == []
    assert body["documents"] == []
    assert body["claim_id"] is None


def test_the_detail_screen_carries_what_the_customer_submitted(
    admin_client: TestClient,
) -> None:
    """The point of the button.

    An operator about to write to an airline needs the passengers, the
    receipts and the answers no database holds -- without opening four tabs.
    The identity number is decrypted on the way out, because filing the
    claim is the only reason it was ever collected.
    """
    check_id = _customer(admin_client)
    _claim_for(
        admin_client,
        check_id,
        booking_reference="ABC123",
        airline_reason="תקלה טכנית",
        expenses=[
            {"category": "HOTEL", "amount": "40.00", "currency": "EUR",
             "description": "לילה אחד"}
        ],
    )

    body = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()

    assert body["booking_reference"] == "ABC123"
    assert body["airline_reason"] == "תקלה טכנית"
    assert body["passengers"][0]["national_id"] == "012345678"
    assert body["expenses"][0]["amount"] == "40.00"
    assert body["expense_totals"] == {"EUR": "40.00"}


def test_an_uploaded_file_can_be_read_back(admin_client: TestClient) -> None:
    """There was no way to read a document back at all before this.

    Files could be uploaded and were then unreachable by anything but a
    shell on the server. A claims operation whose evidence cannot be opened
    is not an operation.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)
    admin_client.post(
        f"/api/v1/claims/{claim['id']}/documents",
        files={"file": ("קבלה.jpg", io.BytesIO(JPEG), "image/jpeg")},
        data={"kind": "RECEIPT"},
    )

    detail = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()
    assert detail["document_count"] == 1

    document_id = detail["documents"][0]["id"]
    response = admin_client.get(
        f"/api/v1/admin/documents/{document_id}", headers=AUTH
    )

    assert response.status_code == 200
    assert response.content == JPEG


def test_a_document_is_served_as_a_download_and_never_cached(
    admin_client: TestClient,
) -> None:
    """Two headers, two different attacks.

    `attachment` stops the browser rendering customer-uploaded bytes inside
    the admin origin -- an uploaded SVG or HTML file would otherwise be a
    script running on the operator's own page, with their key in it.

    `no-store` keeps one customer's passport scan out of any shared cache
    between here and the operator.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)
    admin_client.post(
        f"/api/v1/claims/{claim['id']}/documents",
        files={"file": ("x.jpg", io.BytesIO(JPEG), "image/jpeg")},
        data={"kind": "RECEIPT"},
    )
    document_id = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()["documents"][0]["id"]

    response = admin_client.get(
        f"/api/v1/admin/documents/{document_id}", headers=AUTH
    )

    assert response.headers["content-disposition"].startswith("attachment")
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_hebrew_filename_does_not_break_the_header(
    admin_client: TestClient,
) -> None:
    """Most filenames here are Hebrew, and headers are Latin-1.

    An unencoded Hebrew name makes some clients mangle the response and
    others reject it outright. A quote in the name is worse: it would let
    customer-supplied text close the header value and inject another one.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)
    admin_client.post(
        f"/api/v1/claims/{claim['id']}/documents",
        files={"file": ('קבלה"מלון.jpg', io.BytesIO(JPEG), "image/jpeg")},
        data={"kind": "RECEIPT"},
    )
    detail = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()

    response = admin_client.get(
        f"/api/v1/admin/documents/{detail['documents'][0]['id']}", headers=AUTH
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.isascii()
    assert disposition.count('"') == 2, "the name cannot close the header early"
    # The real name survives in the RFC 5987 parameter, which every browser
    # prefers. Without it the operator downloads "____.jpg" and has to open
    # the file to find out what it is -- safe, and useless.
    assert "filename*=UTF-8''" in disposition
    assert "%D7" in disposition, "the Hebrew is percent-encoded, not discarded"
    # The quote never arrives as a literal: multipart encoding escapes it in
    # transit, so the stored name already reads `%22`. That is the transport
    # protecting us rather than us protecting ourselves, which is exactly why
    # `_ascii_filename` still exists -- a different client, or a filename
    # supplied some other way later, would not have been escaped for us.
    assert detail["documents"][0]["original_filename"] == "קבלה%22מלון.jpg"


def test_a_document_cannot_be_downloaded_without_the_key(
    admin_client: TestClient,
) -> None:
    """The files are the most sensitive thing here -- passports and receipts.

    Listed separately from the router-level guard test because this route
    returns raw bytes rather than JSON, and a mistake here leaks a document
    rather than a row.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)
    admin_client.post(
        f"/api/v1/claims/{claim['id']}/documents",
        files={"file": ("x.jpg", io.BytesIO(JPEG), "image/jpeg")},
        data={"kind": "RECEIPT"},
    )
    document_id = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()["documents"][0]["id"]

    assert admin_client.get(f"/api/v1/admin/documents/{document_id}").status_code == 401


def test_a_filter_narrows_to_the_people_who_filed(admin_client: TestClient) -> None:
    """The two halves of the operator's day, separated.

    "Who needs chasing" is the people with a claim in progress; "who did we
    turn away" is everybody else. One flag, both questions.
    """
    filed = _customer(admin_client, "BA165", contact_email="filed@example.com")
    # The claim's address, not the check's -- a claim overrides it, which the
    # test above asserts deliberately. Setting both keeps this test about the
    # filter rather than about precedence.
    _claim_for(admin_client, filed, contact_email="filed@example.com")
    _customer(admin_client, "XX999", contact_email="refused@example.com")

    with_claim = admin_client.get(
        "/api/v1/admin/customers?has_claim=true", headers=AUTH
    ).json()
    without = admin_client.get(
        "/api/v1/admin/customers?has_claim=false", headers=AUTH
    ).json()

    assert [r["contact_email"] for r in with_claim["items"]] == ["filed@example.com"]
    assert [r["contact_email"] for r in without["items"]] == ["refused@example.com"]


def test_the_counters_agree_with_the_list_they_filter(
    admin_client: TestClient,
) -> None:
    """The counters are also the filters, so they must count the same rows.

    They are computed by a different query from the list -- aggregated in
    SQL, because counting ten thousand ORM objects to show four numbers
    would make the screen slower the more successful the business gets. Two
    queries over one definition is exactly where a drift starts, so the
    visibility rule is shared and this asserts the result.
    """
    filed = _customer(admin_client, "BA165", contact_email="filed@example.com")
    _claim_for(admin_client, filed, contact_email="filed@example.com")
    _customer(admin_client, "XX999", contact_email="refused@example.com")
    # Nobody to contact: must be counted by neither.
    admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    )

    stats = admin_client.get("/api/v1/admin/customers/stats", headers=AUTH).json()
    listed = admin_client.get("/api/v1/admin/customers", headers=AUTH).json()

    assert stats["total"] == listed["total"] == 2
    assert stats["claims"] == 1
    assert stats["eligible"] == 1


def test_the_counters_follow_the_anonymous_toggle(admin_client: TestClient) -> None:
    """Flip the toggle and both numbers must move together.

    Written because the easy mistake is to pass the flag to the list and
    forget it on the counters, which leaves a header saying 1,000 above a
    table of 12 and no way to tell which is lying.
    """
    admin_client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": "BA165", "flight_date": AUG_14},
    )

    without = admin_client.get("/api/v1/admin/customers/stats", headers=AUTH).json()
    with_them = admin_client.get(
        "/api/v1/admin/customers/stats?include_anonymous=true", headers=AUTH
    ).json()

    assert without["total"] == 0
    assert with_them["total"] == 1


def test_stats_is_not_mistaken_for_a_customer_id(admin_client: TestClient) -> None:
    """Route order, asserted.

    `/customers/stats` and `/customers/{check_id}` both match the same
    shape. Declared the other way round, a request for the counters is
    handed to the detail route, which tries to parse "stats" as a UUID and
    answers 422 -- a baffling failure for something that plainly should
    work.
    """
    response = admin_client.get("/api/v1/admin/customers/stats", headers=AUTH)

    assert response.status_code == 200
    assert "total" in response.json()


# --- Hiding, which the screen calls deleting ---------------------------------


def test_a_hidden_customer_leaves_the_list_but_not_the_database(
    admin_client: TestClient,
) -> None:
    """The whole design of the delete button, in one test.

    The operator sees the row go. The record, its claim and its uploaded
    passports stay exactly where they were -- because a checkbox and one
    click is the easiest way in the world to remove fifty customers by
    accident, and undo is impossible once the bytes are gone.
    """
    check_id = _customer(admin_client)
    _claim_for(admin_client, check_id)

    moved = admin_client.post(
        "/api/v1/admin/customers/hide",
        headers=AUTH,
        json={"check_ids": [check_id]},
    ).json()
    assert moved["moved"] == 1

    assert admin_client.get("/api/v1/admin/customers", headers=AUTH).json()["total"] == 0
    # Still fully readable by id, claim and all.
    detail = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()
    assert detail["claim_id"] is not None
    assert detail["hidden_at"] is not None


def test_hidden_customers_have_one_place_to_be_found(
    admin_client: TestClient,
) -> None:
    """Undo needs somewhere to look.

    A hidden row that reappeared among eight hundred others would be
    technically recoverable and practically lost.
    """
    gone = _customer(admin_client, "BA165", contact_email="gone@example.com")
    _customer(admin_client, "LY325", contact_email="here@example.com")
    admin_client.post(
        "/api/v1/admin/customers/hide", headers=AUTH, json={"check_ids": [gone]}
    )

    visible = admin_client.get("/api/v1/admin/customers", headers=AUTH).json()
    put_away = admin_client.get(
        "/api/v1/admin/customers?hidden=true", headers=AUTH
    ).json()

    assert [r["contact_email"] for r in visible["items"]] == ["here@example.com"]
    assert [r["contact_email"] for r in put_away["items"]] == ["gone@example.com"]


def test_restoring_puts_a_customer_back(admin_client: TestClient) -> None:
    """The undo button, end to end."""
    check_id = _customer(admin_client)
    admin_client.post(
        "/api/v1/admin/customers/hide", headers=AUTH, json={"check_ids": [check_id]}
    )

    moved = admin_client.post(
        "/api/v1/admin/customers/restore",
        headers=AUTH,
        json={"check_ids": [check_id]},
    ).json()

    assert moved["moved"] == 1
    assert admin_client.get("/api/v1/admin/customers", headers=AUTH).json()["total"] == 1


def test_the_count_reports_what_moved_not_what_was_asked(
    admin_client: TestClient,
) -> None:
    """An operator selects fifty; six were already hidden by somebody else.

    The honest answer is 44. A screen that echoes the request back as
    though it were the outcome is one people stop believing the first time
    they notice.
    """
    already = _customer(admin_client, "BA165", contact_email="a@example.com")
    fresh = _customer(admin_client, "LY325", contact_email="b@example.com")
    admin_client.post(
        "/api/v1/admin/customers/hide", headers=AUTH, json={"check_ids": [already]}
    )

    again = admin_client.post(
        "/api/v1/admin/customers/hide",
        headers=AUTH,
        json={"check_ids": [already, fresh]},
    ).json()

    assert again["moved"] == 1, "only the one that was still visible"


def test_hidden_customers_are_left_out_of_the_counters(
    admin_client: TestClient,
) -> None:
    """Deleting a row must make the number above the table go down.

    Written because the counters are a separate query: it is entirely
    possible to filter the list and forget the aggregate, leaving a header
    that insists on customers the operator can no longer see.
    """
    check_id = _customer(admin_client)
    before = admin_client.get("/api/v1/admin/customers/stats", headers=AUTH).json()
    admin_client.post(
        "/api/v1/admin/customers/hide", headers=AUTH, json={"check_ids": [check_id]}
    )
    after = admin_client.get("/api/v1/admin/customers/stats", headers=AUTH).json()

    assert before["total"] == 1
    assert after["total"] == 0


def test_hiding_requires_the_key(admin_client: TestClient) -> None:
    """A write endpoint, so worth its own test rather than the router sweep."""
    check_id = _customer(admin_client)
    assert (
        admin_client.post(
            "/api/v1/admin/customers/hide", json={"check_ids": [check_id]}
        ).status_code
        == 401
    )


def test_an_empty_selection_is_refused_rather_than_silently_doing_nothing(
    admin_client: TestClient,
) -> None:
    """A bulk action with no ids is a bug in the caller, not a no-op.

    Answering 200/"0 moved" would let a broken select-all ship unnoticed.
    """
    assert (
        admin_client.post(
            "/api/v1/admin/customers/hide", headers=AUTH, json={"check_ids": []}
        ).status_code
        == 422
    )


# --- The claim lifecycle column ----------------------------------------------


def test_a_claim_can_be_moved_along_its_lifecycle(admin_client: TestClient) -> None:
    """The eight stages existed and nothing could set them.

    The status column only ever read DRAFT or SUBMITTED whatever had
    really happened, which made it decoration -- and an operator with a
    decorative status column keeps the real one in a spreadsheet.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)

    response = admin_client.patch(
        f"/api/v1/admin/claims/{claim['id']}/status",
        headers=AUTH,
        json={"status": "SENT_TO_AIRLINE"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SENT_TO_AIRLINE"
    row = admin_client.get("/api/v1/admin/customers", headers=AUTH).json()["items"][0]
    assert row["claim_status"] == "SENT_TO_AIRLINE"


def test_a_claim_can_go_backwards(admin_client: TestClient) -> None:
    """No transition rules, deliberately.

    Real claims go backwards: an airline asks for another document, a
    customer withdraws and refiles. A one-way pipeline would leave an
    operator looking at the correct value and unable to set it, which is
    how the real status ends up somewhere this system cannot see.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)
    for stage in ("SETTLED", "IN_REVIEW", "DRAFT"):
        assert (
            admin_client.patch(
                f"/api/v1/admin/claims/{claim['id']}/status",
                headers=AUTH,
                json={"status": stage},
            ).status_code
            == 200
        )


def test_an_invented_status_is_refused(admin_client: TestClient) -> None:
    """A typo in a dashboard must not create a ninth stage no report counts."""
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)

    response = admin_client.patch(
        f"/api/v1/admin/claims/{claim['id']}/status",
        headers=AUTH,
        json={"status": "PROBABLY_FINE"},
    )

    assert response.status_code == 422


def test_a_document_whose_bytes_are_gone_answers_410_not_500(
    admin_client: TestClient, admin_settings
) -> None:  # type: ignore[no-untyped-def]
    """The exact failure a customer hit, reproduced.

    `upload_dir` defaulted to a path inside the container, and a container
    on Render is rebuilt from its image on every deploy -- so every
    receipt a customer uploaded was destroyed by the next push. Nothing
    noticed, because until the operator console nothing had ever read a
    file back.

    410 and not 404: the record exists and is correct. 410 and not 500:
    this is a known state of the world, not a crash, and the operator
    needs to be told which document to ask for again rather than shown a
    stack trace.
    """
    check_id = _customer(admin_client)
    claim = _claim_for(admin_client, check_id)
    admin_client.post(
        f"/api/v1/claims/{claim['id']}/documents",
        files={"file": ("x.jpg", io.BytesIO(JPEG), "image/jpeg")},
        data={"kind": "RECEIPT"},
    )
    document_id = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()["documents"][0]["id"]
    assert (
        admin_client.get(
            f"/api/v1/admin/documents/{document_id}", headers=AUTH
        ).status_code
        == 200
    )

    # Exactly what a deploy does to an ephemeral filesystem.
    for path in admin_settings.upload_dir.rglob("*"):
        if path.is_file():
            path.unlink()

    response = admin_client.get(
        f"/api/v1/admin/documents/{document_id}", headers=AUTH
    )

    assert response.status_code == 410
    # The row survives. It is still the evidence that the customer sent us
    # something, and deleting it would destroy the only record that they
    # did.
    detail = admin_client.get(
        f"/api/v1/admin/customers/{check_id}", headers=AUTH
    ).json()
    assert detail["document_count"] == 1


# --- The archive endpoint ----------------------------------------------------
#
# These exist because the repository was tested thoroughly and the ROUTE
# was not, and a 500 shipped to production.
#
# `search_flights` grew a third return value when paging was added. The
# repository tests were updated; the route still unpacked two, raised
# ValueError on every single request, and the operator saw "we could not
# load the list". Nothing in the suite touched the endpoint, so nothing
# noticed.
#
# The lesson is cheap to encode: call the thing over HTTP.


def test_the_archive_endpoint_answers_at_all(admin_client: TestClient) -> None:
    """A 200 with the documented shape.

    Deliberately the dullest test in the file. It would have caught a
    ValueError that made the whole screen unusable, which is worth more
    than any assertion about the contents.
    """
    _customer(admin_client, "BA165")

    response = admin_client.get("/api/v1/admin/flights", headers=AUTH)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items", "total", "truncated"}


def test_every_query_this_screen_can_send_is_answered(
    admin_client: TestClient,
) -> None:
    """Each control on the page, exercised through the API.

    A filter that 500s is indistinguishable from a backend that is down,
    and the page says the same sentence for both -- so each combination
    the UI can produce is worth one line here.
    """
    _customer(admin_client, "BA165")

    for query in (
        "",
        "?number=BA165",
        "?date=2026-08-14",
        "?disrupted_only=true",
        "?number=ba165&disrupted_only=false",
        "?since=2026-08-01&until=2026-08-31",
        "?limit=1&offset=0",
        "?limit=1&offset=5",
    ):
        response = admin_client.get(f"/api/v1/admin/flights{query}", headers=AUTH)
        assert response.status_code == 200, f"{query} -> {response.text}"


def test_a_flight_is_returned_with_the_fields_the_screen_renders(
    admin_client: TestClient,
) -> None:
    """The columns, pinned.

    The screen shows scheduled and actual times for both ends, the
    source, and whether the rules could use the record. A field quietly
    renamed in the schema would render as an empty column rather than as
    an error, which is the kind of breakage nobody reports.
    """
    _customer(admin_client, "BA165")

    body = admin_client.get(
        "/api/v1/admin/flights?number=BA165", headers=AUTH
    ).json()

    assert body["items"], "the fake provider's flight should be archived"
    row = body["items"][0]
    for field in (
        "flight_number",
        "flight_date",
        "origin_iata",
        "destination_iata",
        "scheduled_departure",
        "actual_departure",
        "scheduled_arrival",
        "actual_arrival",
        "status",
        "provider",
        "usable",
        "raw",
    ):
        assert field in row, field


def test_paging_through_the_endpoint_does_not_repeat_a_flight(
    admin_client: TestClient,
) -> None:
    """Offset reaches the second page rather than re-serving the first.

    The repository test covers the arithmetic; this covers the wiring,
    which is the half that broke. `offset` was accepted by the route and
    never passed on.
    """
    for number in ("BA165", "LY325", "LH687"):
        _customer(admin_client, number)

    # An explicit date: the default browse is the last seven days, and the
    # fixture flies in August.
    first = admin_client.get(
        f"/api/v1/admin/flights?date={AUG_14}&limit=1&offset=0", headers=AUTH
    ).json()
    second = admin_client.get(
        f"/api/v1/admin/flights?date={AUG_14}&limit=1&offset=1", headers=AUTH
    ).json()

    assert first["total"] >= 2
    assert first["items"][0] != second["items"][0]
