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
    "path", ["/api/v1/admin/summary", "/api/v1/admin/checks", "/api/v1/admin/claims"]
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
