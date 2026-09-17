"""Tests for claims, passengers, expenses and documents.

What happens after a check says yes. The themes: a claim is assembled over
several sittings rather than in one shot, money keeps its currency, and the
database refuses shapes that would be nonsense to a human reading them later.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.claims import (
    ClaimError,
    add_document,
    add_expense,
    add_passenger,
    create_claim,
    expense_totals,
    find_claim_by_reference,
    find_claim_for_check,
    generate_reference,
    get_claim,
    list_claims,
    set_status,
    submit_claim,
)
from app.db.models import ClaimStatus, DocumentKind, EligibilityCheck, ExpenseCategory
from app.db.repositories import record_check
from app.db.session import (
    create_all,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from app.providers.registry import build_provider
from app.services.eligibility import check as run_check

AUG_14 = date(2026, 8, 14)


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    with session_scope(create_session_factory(engine)) as session:
        yield session


async def eligible_check(session: Session, number: str = "BA165") -> EligibilityCheck:
    outcome = await run_check(build_provider("fake"), number, AUG_14)
    return record_check(session, outcome, contact_email="noam@example.com")


async def a_claim(session: Session, **kwargs: object):  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "contact_name": "Noam Hasson",
        "contact_email": "noam@example.com",
    }
    defaults.update(kwargs)
    return create_claim(session, await eligible_check(session), **defaults)  # type: ignore[arg-type]


# --- The claim reference -----------------------------------------------------


def test_references_are_human_quotable() -> None:
    """Customers ring up and read this out. Nobody reads out a UUID."""
    reference = generate_reference(date(2026, 8, 14))
    assert reference.startswith("FS-2026-")
    assert len(reference) == 14


def test_references_avoid_ambiguous_characters() -> None:
    """No I, O, 0 or 1.

    These get read over the phone and copied off screenshots, and those four
    are the ones people get wrong. Excluding them costs a little entropy and
    saves a support conversation.
    """
    body = "".join(generate_reference()[8:] for _ in range(200))
    assert not (set(body) & set("IO01"))


def test_references_are_random_not_sequential(session: Session) -> None:
    """A sequential reference tells every customer how many claims you have
    ever handled, and lets them read somebody else's by subtracting one."""
    assert len({generate_reference() for _ in range(50)}) == 50


async def test_a_claim_can_be_found_the_way_a_customer_quotes_it(
    session: Session,
) -> None:
    """Typed from a screenshot, so casing and stray spaces must not matter."""
    claim = await a_claim(session)
    for typed in (claim.reference, claim.reference.lower(), f" {claim.reference} "):
        found = find_claim_by_reference(session, typed)
        assert found is not None and found.id == claim.id


# --- Creating ----------------------------------------------------------------


async def test_a_claim_starts_as_a_draft(session: Session) -> None:
    """People get halfway through a form and come back tomorrow."""
    claim = await a_claim(session)
    assert claim.status == ClaimStatus.DRAFT.value
    assert claim.submitted_at is None


async def test_the_claim_does_not_copy_the_verdict(session: Session) -> None:
    """It links to the check instead.

    The verdict, the flight snapshot and the reasoning all live on the check. A
    copy here would be a second version of the truth, and the two would
    eventually disagree -- at which point nobody knows which was shown to the
    customer.
    """
    claim = await a_claim(session)
    assert claim.check.verdict == "ELIGIBLE"
    assert not hasattr(claim, "verdict")
    assert claim.check.best_amount == Decimal("520.00")


async def test_one_check_cannot_have_two_claims(session: Session) -> None:
    """The second attempt is almost always someone who lost the first tab.

    Telling them the existing reference is more useful than either silently
    making a duplicate or showing a database error.
    """
    check = await eligible_check(session)
    first = create_claim(
        session, check, contact_name="Noam", contact_email="noam@example.com"
    )
    with pytest.raises(ClaimError, match=first.reference):
        create_claim(
            session, check, contact_name="Noam", contact_email="noam@example.com"
        )


async def test_contact_details_are_required_and_normalised(session: Session) -> None:
    """We have to be able to reach them; everything else can wait."""
    claim = await a_claim(
        session, contact_name="  Noam Hasson ", contact_email=" Noam@Example.COM "
    )
    assert claim.contact_name == "Noam Hasson"
    assert claim.contact_email == "noam@example.com"

    check = await eligible_check(session, "LY325")
    for bad in ({"contact_name": "  "}, {"contact_email": ""}):
        payload = {"contact_name": "N", "contact_email": "n@example.com", **bad}
        with pytest.raises(ClaimError):
            create_claim(session, check, **payload)  # type: ignore[arg-type]


async def test_the_two_questions_no_api_can_answer_are_stored(
    session: Session,
) -> None:
    """Why the flight was late, and how much notice a cancellation got.

    Both decide eligibility, neither appears in any flight database, and both
    can only come from the person who was actually there.
    """
    claim = await a_claim(
        session,
        airline_reason="They said a technical fault with the aircraft.",
        cancellation_notice_days=3,
    )
    assert "technical fault" in claim.airline_reason
    assert claim.cancellation_notice_days == 3


# --- Passengers --------------------------------------------------------------


async def test_several_passengers_on_one_claim(session: Session) -> None:
    """Compensation is per passenger, so a family of four is four awards.

    That is exactly why this is a table and not a name field on the claim.
    """
    claim = await a_claim(session)
    add_passenger(session, claim, full_name="Noam Hasson", national_id="012345678")
    add_passenger(session, claim, full_name="Dana Hasson", national_id="087654321")
    add_passenger(session, claim, full_name="Ari Hasson", is_minor=True)

    session.refresh(claim)
    assert len(claim.passengers) == 3
    assert sum(p.is_minor for p in claim.passengers) == 1


async def test_a_passenger_needs_a_name(session: Session) -> None:
    claim = await a_claim(session)
    with pytest.raises(ClaimError, match="full name"):
        add_passenger(session, claim, full_name="   ")


async def test_an_id_number_is_optional(session: Session) -> None:
    """Children often have none, and demanding one would block the claim."""
    claim = await a_claim(session)
    passenger = add_passenger(session, claim, full_name="Ari Hasson", is_minor=True)
    assert passenger.national_id is None


# --- Expenses ----------------------------------------------------------------


async def test_expenses_keep_the_currency_they_were_paid_in(
    session: Session,
) -> None:
    """A hotel bill in Frankfurt is in euro whatever the award is denominated in.

    Converting it here would destroy the only number the receipt actually
    proves.
    """
    claim = await a_claim(session)
    add_expense(
        session, claim, category=ExpenseCategory.HOTEL, amount="180.00", currency="EUR",
        description="One night at the airport hotel", incurred_on=AUG_14,
    )
    add_expense(
        session, claim, category=ExpenseCategory.TRANSPORT, amount="240.50",
        currency="ILS", description="Taxi home at 3am",
    )
    session.refresh(claim)
    assert expense_totals(claim) == {"EUR": Decimal("180.00"), "ILS": Decimal("240.50")}


async def test_totals_are_never_summed_across_currencies(session: Session) -> None:
    """Euro and shekels do not add up to a number.

    Inventing a rate to make them would be quietly making up a figure somebody
    later has to defend to an airline.
    """
    claim = await a_claim(session)
    add_expense(session, claim, category="MEAL", amount="12.00", currency="EUR")
    add_expense(session, claim, category="MEAL", amount="40.00", currency="ILS")
    session.refresh(claim)

    totals = expense_totals(claim)
    assert len(totals) == 2
    assert Decimal("52.00") not in totals.values()


async def test_expense_amounts_are_exact(session: Session) -> None:
    """Same guarantee as compensation, one layer down."""
    claim = await a_claim(session)
    add_expense(session, claim, category="MEAL", amount="0.10", currency="EUR")
    add_expense(session, claim, category="MEAL", amount="0.20", currency="EUR")
    session.expire_all()

    reloaded = get_claim(session, claim.id)
    assert reloaded is not None
    assert expense_totals(reloaded)["EUR"] == Decimal("0.30")


async def test_a_float_amount_is_refused(session: Session) -> None:
    """The same refusal Money makes: a float that reaches us has already lost
    precision, and converting it would only launder the error."""
    claim = await a_claim(session)
    with pytest.raises(ClaimError, match="must not be floats"):
        add_expense(session, claim, category="MEAL", amount=12.5, currency="EUR")  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", ["0", "-5.00"])
async def test_an_expense_must_be_positive(session: Session, amount: str) -> None:
    claim = await a_claim(session)
    with pytest.raises(ClaimError, match="positive amount"):
        add_expense(session, claim, category="MEAL", amount=amount, currency="EUR")


async def test_an_unknown_category_is_refused(session: Session) -> None:
    """A fixed list, because the point of collecting expenses is to total them
    and argue they were reasonable -- which fails if one person writes "taxi"
    and the next writes "Uber home"."""
    claim = await a_claim(session)
    with pytest.raises(ValueError):
        add_expense(session, claim, category="SOUVENIRS", amount="10", currency="EUR")


# --- Documents ---------------------------------------------------------------


async def test_a_receipt_can_be_attached_to_its_expense(session: Session) -> None:
    """So an airline disputing one line item can be shown the one receipt."""
    claim = await a_claim(session)
    hotel = add_expense(
        session, claim, category="HOTEL", amount="180.00", currency="EUR"
    )
    document = add_document(
        session, claim, kind=DocumentKind.RECEIPT,
        original_filename="hotel.pdf", stored_path="uploads/ab/cd/ef.pdf",
        content_type="application/pdf", size_bytes=84_213, expense=hotel,
    )
    assert document.expense_id == hotel.id


async def test_a_booking_document_belongs_to_the_claim_not_an_expense(
    session: Session,
) -> None:
    claim = await a_claim(session)
    document = add_document(
        session, claim, kind=DocumentKind.BOOKING,
        original_filename="confirmation.pdf", stored_path="uploads/12/34/56.pdf",
        content_type="application/pdf", size_bytes=22_100,
    )
    assert document.expense_id is None


async def test_the_stored_path_is_not_the_filename(session: Session) -> None:
    """A filename from a browser is attacker-controlled input, and one
    containing ../ is the oldest trick there is.

    The storage layer decides the path; this column simply records it. The
    original name is kept only so the customer recognises their own file.
    """
    claim = await a_claim(session)
    document = add_document(
        session, claim, kind="RECEIPT",
        original_filename="../../etc/passwd", stored_path="uploads/aa/bb/cc.bin",
        content_type="application/octet-stream", size_bytes=10,
    )
    assert document.original_filename == "../../etc/passwd"  # kept verbatim
    assert ".." not in document.stored_path  # but never used as a path


async def test_an_empty_upload_is_refused(session: Session) -> None:
    claim = await a_claim(session)
    with pytest.raises(ClaimError, match="cannot be empty"):
        add_document(
            session, claim, kind="RECEIPT", original_filename="x.pdf",
            stored_path="p", content_type="application/pdf", size_bytes=0,
        )


async def test_a_receipt_cannot_be_attached_to_another_claims_expense(
    session: Session,
) -> None:
    """Otherwise one customer's receipt could end up filed under another's
    claim, which is both a data leak and a wrong total."""
    first = await a_claim(session)
    second = create_claim(
        session, await eligible_check(session, "LY325"),
        contact_name="Dana", contact_email="dana@example.com",
    )
    theirs = add_expense(session, second, category="MEAL", amount="9", currency="EUR")

    with pytest.raises(ClaimError, match="different claim"):
        add_document(
            session, first, kind="RECEIPT", original_filename="r.pdf",
            stored_path="p", content_type="application/pdf", size_bytes=10,
            expense=theirs,
        )


# --- Submitting --------------------------------------------------------------


async def test_submitting_records_when(session: Session) -> None:
    claim = await a_claim(session)
    add_passenger(session, claim, full_name="Noam Hasson")
    submit_claim(session, claim)

    assert claim.status == ClaimStatus.SUBMITTED.value
    assert claim.submitted_at is not None


async def test_an_empty_claim_cannot_be_submitted(session: Session) -> None:
    """A submission with no passengers is not a claim.

    Letting one through means somebody has to chase it later, by which time the
    customer has forgotten they ever started.
    """
    claim = await a_claim(session)
    with pytest.raises(ClaimError, match="at least one passenger"):
        submit_claim(session, claim)


async def test_a_claim_cannot_be_submitted_twice(session: Session) -> None:
    """Double-clicking Submit is the commonest thing a user does."""
    claim = await a_claim(session)
    add_passenger(session, claim, full_name="Noam Hasson")
    submit_claim(session, claim)

    with pytest.raises(ClaimError, match="already been submitted"):
        submit_claim(session, claim)


# --- Deleting and relationships ----------------------------------------------


async def test_deleting_a_claim_takes_its_children_with_it(
    session: Session,
) -> None:
    """A passenger with no claim is an orphan nobody will ever find, and under
    the GDPR "delete my claim" has to mean the ID numbers go too."""
    claim = await a_claim(session)
    add_passenger(session, claim, full_name="Noam Hasson", national_id="012345678")
    expense = add_expense(session, claim, category="MEAL", amount="12", currency="EUR")
    add_document(
        session, claim, kind="RECEIPT", original_filename="r.pdf", stored_path="p",
        content_type="application/pdf", size_bytes=10, expense=expense,
    )
    claim_id = claim.id

    session.delete(claim)
    session.flush()

    from app.db.models import Document, Expense, Passenger

    assert get_claim(session, claim_id) is None
    for model in (Passenger, Expense, Document):
        assert session.query(model).count() == 0


async def test_a_check_with_a_claim_cannot_be_deleted(session: Session) -> None:
    """The check holds the verdict and the evidence behind it.

    Deleting it would leave a claim that cannot say why it exists, so the
    foreign key refuses.
    """
    from sqlalchemy.exc import IntegrityError

    check = await eligible_check(session)
    create_claim(session, check, contact_name="N", contact_email="n@example.com")

    session.delete(check)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# --- Listing -----------------------------------------------------------------


async def test_claims_are_listed_newest_first_and_filtered(
    session: Session,
) -> None:
    first = await a_claim(session)
    add_passenger(session, first, full_name="Noam Hasson")
    submit_claim(session, first)
    create_claim(
        session, await eligible_check(session, "LY325"),
        contact_name="Dana", contact_email="dana@example.com",
    )
    session.flush()

    assert len(list_claims(session)) == 2
    assert len(list_claims(session, status=ClaimStatus.SUBMITTED.value)) == 1
    assert len(list_claims(session, contact_email="DANA@example.com")) == 1


async def test_the_claim_for_a_check_can_be_found(session: Session) -> None:
    check = await eligible_check(session)
    claim = create_claim(
        session, check, contact_name="N", contact_email="n@example.com"
    )
    assert find_claim_for_check(session, check.id) is claim
    assert find_claim_for_check(session, uuid.uuid4()) is None


async def test_status_can_be_advanced(session: Session) -> None:
    claim = await a_claim(session)
    set_status(session, claim, ClaimStatus.SENT_TO_AIRLINE)
    assert claim.status == "SENT_TO_AIRLINE"
