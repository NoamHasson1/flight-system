"""Tests for claim submission and document upload.

Two themes: a claim is built from a check and cannot outrun it, and an uploaded
file is treated as hostile until proven otherwise.
"""

import io

import pytest
from fastapi.testclient import TestClient

AUG_14 = "2026-08-14"

PDF = b"%PDF-1.7\nfake but correctly signed\n%%EOF"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def a_check(client: TestClient, number: str = "BA165") -> str:
    response = client.post(
        "/api/v1/eligibility/check",
        json={"flight_number": number, "flight_date": AUG_14},
    )
    return response.json()["check_id"]


def a_claim(client: TestClient, **overrides: object) -> dict:  # type: ignore[type-arg]
    payload: dict[str, object] = {
        "check_id": a_check(client),
        "contact_name": "Noam Hasson",
        "contact_email": "noam@example.com",
        "passengers": [{"full_name": "Noam Hasson", "national_id": "012345678"}],
    }
    payload.update(overrides)
    response = client.post("/api/v1/claims", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --- Creating ----------------------------------------------------------------


def test_a_claim_is_created_from_a_check(client: TestClient) -> None:
    claim = a_claim(client)

    assert claim["status"] == "DRAFT"
    assert claim["reference"].startswith("FS-")
    assert len(claim["passengers"]) == 1
    assert claim["submitted_at"] is None


def test_passengers_and_expenses_arrive_in_one_call(client: TestClient) -> None:
    """One request rather than four.

    A claim assembled over several round trips can fail on the third and leave
    a half-built record nobody can finish and nobody will ever chase.
    """
    claim = a_claim(
        client,
        passengers=[
            {"full_name": "Noam Hasson", "national_id": "012345678"},
            {"full_name": "Dana Hasson", "national_id": "087654321"},
            {"full_name": "Ari Hasson", "is_minor": True},
        ],
        expenses=[
            {"category": "HOTEL", "amount": "180.00", "currency": "EUR",
             "description": "Airport hotel"},
            {"category": "TRANSPORT", "amount": "240.50", "currency": "ILS",
             "description": "Taxi home"},
            {"category": "MEAL", "amount": "46.20", "currency": "EUR"},
        ],
    )

    assert len(claim["passengers"]) == 3
    assert len(claim["expenses"]) == 3
    assert sum(p["is_minor"] for p in claim["passengers"]) == 1


def test_expense_totals_are_per_currency(client: TestClient) -> None:
    """Euro and shekels do not add up to a number.

    Inventing a rate to make them would be making up a figure somebody later
    has to defend to an airline.
    """
    claim = a_claim(
        client,
        expenses=[
            {"category": "HOTEL", "amount": "180.00", "currency": "EUR"},
            {"category": "MEAL", "amount": "46.20", "currency": "EUR"},
            {"category": "TRANSPORT", "amount": "240.50", "currency": "ILS"},
        ],
    )
    assert claim["expense_totals"] == {"EUR": "226.20", "ILS": "240.50"}


def test_the_two_questions_no_api_can_answer_are_captured(
    client: TestClient,
) -> None:
    """Why the flight was late, and how much notice a cancellation got."""
    claim = a_claim(
        client,
        airline_reason="They said a technical fault with the aircraft.",
        cancellation_notice="UNDER_A_WEEK",
    )
    assert "technical fault" in claim["airline_reason"]
    assert claim["cancellation_notice"] == "UNDER_A_WEEK"


def test_a_claim_needs_a_real_check(client: TestClient) -> None:
    response = client.post(
        "/api/v1/claims",
        json={
            "check_id": "00000000-0000-0000-0000-000000000000",
            "contact_name": "Noam", "contact_email": "n@example.com",
        },
    )
    assert response.status_code == 404


@pytest.mark.parametrize("number", ["XX999", "FR1234"])
def test_a_check_that_found_no_flight_cannot_become_a_claim(
    client: TestClient, number: str
) -> None:
    """NOT_FOUND and AMBIGUOUS never identified a flight, so there is nothing
    to claim about yet."""
    response = client.post(
        "/api/v1/claims",
        json={
            "check_id": a_check(client, number),
            "contact_name": "Noam", "contact_email": "n@example.com",
        },
    )
    assert response.status_code == 409
    assert "nothing to claim" in response.json()["detail"]


def test_a_not_eligible_check_can_still_become_a_claim(client: TestClient) -> None:
    """Deliberate, and worth stating.

    We told that customer no, but our verdict rests on facts we could not see --
    why the flight was late, what the airline actually said. Refusing to let
    them proceed would make our estimate final, and it is not.
    """
    response = client.post(
        "/api/v1/claims",
        json={
            "check_id": a_check(client, "LY325"),
            "contact_name": "Avi Cohen", "contact_email": "avi@example.com",
            "passengers": [{"full_name": "Avi Cohen"}],
        },
    )
    assert response.status_code == 201


def test_one_check_cannot_have_two_claims(client: TestClient) -> None:
    """The second attempt is almost always someone who lost the first tab, so
    the error names the reference they already have."""
    check_id = a_check(client)
    payload = {
        "check_id": check_id, "contact_name": "Noam",
        "contact_email": "n@example.com",
    }
    first = client.post("/api/v1/claims", json=payload).json()

    second = client.post("/api/v1/claims", json=payload)
    assert second.status_code == 409
    assert first["reference"] in second.json()["detail"]


# --- Input validation --------------------------------------------------------


def test_an_expense_amount_is_a_string_not_a_number(client: TestClient) -> None:
    """The same refusal Money makes, at the edge of the system."""
    claim = a_claim(
        client, expenses=[{"category": "MEAL", "amount": "0.10", "currency": "EUR"}]
    )
    assert claim["expenses"][0]["amount"] == "0.10"
    assert isinstance(claim["expenses"][0]["amount"], str)


@pytest.mark.parametrize("amount", ["0", "-5.00", "abc", "999999"])
def test_a_nonsense_expense_amount_is_refused(
    client: TestClient, amount: str
) -> None:
    """999999 is the typo guard: 18000 entered instead of 180.00 is far
    commoner than a genuine six-figure taxi fare."""
    response = client.post(
        "/api/v1/claims",
        json={
            "check_id": a_check(client), "contact_name": "Noam",
            "contact_email": "n@example.com",
            "expenses": [{"category": "MEAL", "amount": amount, "currency": "EUR"}],
        },
    )
    assert response.status_code == 422


def test_an_unknown_expense_category_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/claims",
        json={
            "check_id": a_check(client), "contact_name": "Noam",
            "contact_email": "n@example.com",
            "expenses": [
                {"category": "SOUVENIRS", "amount": "10", "currency": "EUR"}
            ],
        },
    )
    assert response.status_code == 422


def test_contact_details_are_required_on_a_claim(client: TestClient) -> None:
    """Unlike the check, where demanding them would lose most visitors. By this
    point there is something worth claiming and we must be able to reach them."""
    response = client.post(
        "/api/v1/claims",
        json={"check_id": a_check(client), "contact_name": "", "contact_email": "x"},
    )
    assert response.status_code == 422


# --- Uploading ---------------------------------------------------------------


def upload(client: TestClient, claim_id: str, content: bytes, name: str,
           content_type: str, **data: object):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/claims/{claim_id}/documents",
        files={"file": (name, io.BytesIO(content), content_type)},
        data=data,
    )


def test_a_booking_confirmation_can_be_uploaded(client: TestClient) -> None:
    claim = a_claim(client)
    response = upload(
        client, claim["id"], PDF, "confirmation.pdf", "application/pdf",
        kind="BOOKING",
    )

    assert response.status_code == 201
    document = response.json()["document"]
    assert document["kind"] == "BOOKING"
    assert document["original_filename"] == "confirmation.pdf"
    assert document["size_bytes"] == len(PDF)
    assert document["expense_id"] is None


def test_a_receipt_can_be_attached_to_its_expense(client: TestClient) -> None:
    """So an airline disputing one line item can be shown one receipt."""
    claim = a_claim(
        client, expenses=[{"category": "HOTEL", "amount": "180.00", "currency": "EUR"}]
    )
    expense_id = claim["expenses"][0]["id"]

    response = upload(
        client, claim["id"], PDF, "hotel.pdf", "application/pdf",
        kind="RECEIPT", expense_id=expense_id,
    )
    assert response.status_code == 201
    assert response.json()["document"]["expense_id"] == expense_id

    reloaded = client.get(f"/api/v1/claims/{claim['id']}").json()
    assert reloaded["expenses"][0]["document_count"] == 1


def test_the_original_filename_never_becomes_a_path(client: TestClient) -> None:
    """The oldest trick there is.

    The name is kept verbatim so the customer recognises their own file, and is
    never used to build a path -- storage generates a random one.
    """
    claim = a_claim(client)
    response = upload(
        client, claim["id"], PDF, "../../../etc/passwd", "application/pdf"
    )

    assert response.status_code == 201
    assert response.json()["document"]["original_filename"] == "../../../etc/passwd"

    from pathlib import Path

    root = Path(client.app.state.settings.upload_dir)  # type: ignore[attr-defined]
    assert not (root.parent.parent / "etc" / "passwd").exists()
    assert len(list(root.rglob("*.pdf"))) == 1


def test_an_executable_labelled_as_a_pdf_is_refused(client: TestClient) -> None:
    """The check that a naive implementation gets wrong.

    Rejecting only when the bytes look like some OTHER known format lets
    anything unrecognised straight through -- including a Windows executable
    labelled application/pdf. For every format we can verify, the signature
    must match.
    """
    claim = a_claim(client)
    response = upload(
        client, claim["id"], b"MZ\x90\x00" + b"\x00" * 60, "invoice.pdf",
        "application/pdf",
    )

    assert response.status_code == 422
    assert "labelled application/pdf" in response.json()["detail"]


def test_a_script_labelled_as_an_image_is_refused(client: TestClient) -> None:
    claim = a_claim(client)
    response = upload(
        client, claim["id"], b"<?php system($_GET[0]); ?>", "receipt.jpg", "image/jpeg"
    )
    assert response.status_code == 422


def test_a_disallowed_type_is_refused(client: TestClient) -> None:
    """An allowlist, not a blocklist. A blocklist is a list of the attacks
    somebody already thought of."""
    claim = a_claim(client)
    response = upload(
        client, claim["id"], b"#!/bin/sh\nrm -rf /", "run.sh", "application/x-sh"
    )
    assert response.status_code == 422
    assert "PDF or a photo" in response.json()["detail"]


def test_an_oversized_file_is_refused_with_advice(client: TestClient) -> None:
    claim = a_claim(client)
    response = upload(
        client, claim["id"], PDF + b"x" * (11 * 1024 * 1024), "huge.pdf",
        "application/pdf",
    )
    assert response.status_code == 422
    assert "photographing the receipt" in response.json()["detail"]


def test_an_empty_file_is_refused(client: TestClient) -> None:
    claim = a_claim(client)
    assert upload(client, claim["id"], b"", "empty.pdf", "application/pdf").status_code == 422


def test_a_photo_receipt_is_accepted(client: TestClient) -> None:
    """The commonest real upload by far."""
    claim = a_claim(client)
    response = upload(client, claim["id"], JPEG, "IMG_4821.JPG", "image/jpeg")
    assert response.status_code == 201
    assert response.json()["document"]["content_type"] == "image/jpeg"


def test_a_receipt_cannot_be_attached_to_another_claims_expense(
    client: TestClient,
) -> None:
    """Otherwise one customer's receipt lands under another's claim, which is
    both a data leak and a wrong total."""
    mine = a_claim(client)
    theirs = a_claim(
        client,
        check_id=a_check(client, "LY325"),
        contact_email="dana@example.com",
        expenses=[{"category": "MEAL", "amount": "9.00", "currency": "EUR"}],
    )

    response = upload(
        client, mine["id"], PDF, "r.pdf", "application/pdf",
        expense_id=theirs["expenses"][0]["id"],
    )
    assert response.status_code == 404


def test_uploading_to_an_unknown_claim_is_404(client: TestClient) -> None:
    response = upload(
        client, "00000000-0000-0000-0000-000000000000", PDF, "r.pdf",
        "application/pdf",
    )
    assert response.status_code == 404


# --- Reading and submitting --------------------------------------------------


def test_a_claim_can_be_read_back_by_reference(client: TestClient) -> None:
    """Typed off a screenshot, so casing and spacing must not matter."""
    claim = a_claim(client)
    for typed in (claim["reference"], claim["reference"].lower()):
        response = client.get(f"/api/v1/claims/by-reference/{typed}")
        assert response.status_code == 200
        assert response.json()["id"] == claim["id"]


def test_by_reference_is_matched_before_the_id_route(client: TestClient) -> None:
    """Route order matters.

    FastAPI matches in registration order, so with /{claim_id} declared first
    "by-reference" would be parsed as a UUID and the request would fail
    validation instead of reaching the handler.
    """
    response = client.get("/api/v1/claims/by-reference/FS-2026-NOPEXX")
    assert response.status_code == 404
    assert "No claim with the reference" in response.json()["detail"]


def test_submitting_records_when(client: TestClient) -> None:
    claim = a_claim(client)
    response = client.post(f"/api/v1/claims/{claim['id']}/submit")

    assert response.status_code == 200
    assert response.json()["status"] == "SUBMITTED"
    assert response.json()["submitted_at"] is not None


def test_an_empty_claim_cannot_be_submitted(client: TestClient) -> None:
    """A submission with no passengers is not a claim."""
    claim = a_claim(client, passengers=[])
    response = client.post(f"/api/v1/claims/{claim['id']}/submit")

    assert response.status_code == 409
    assert "at least one passenger" in response.json()["detail"]


def test_a_claim_cannot_be_submitted_twice(client: TestClient) -> None:
    """Double-clicking Submit is the commonest thing a user does."""
    claim = a_claim(client)
    client.post(f"/api/v1/claims/{claim['id']}/submit")

    second = client.post(f"/api/v1/claims/{claim['id']}/submit")
    assert second.status_code == 409
    assert "already been submitted" in second.json()["detail"]


def test_the_claim_links_back_to_its_check(client: TestClient) -> None:
    """The verdict lives on the check and is never copied here, so the link is
    the only way back to why this claim exists."""
    claim = a_claim(client)
    check = client.get(f"/api/v1/eligibility/checks/{claim['check_id']}").json()
    assert check["verdict"] == "ELIGIBLE"
    assert check["best_award"]["formatted"] == "£520.00"
