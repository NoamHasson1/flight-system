"""Identity numbers, encrypted at rest.

The threat is somebody obtaining the database file: a stolen laptop, a copied
backup, a misconfigured bucket, an operator browsing tables, or the file being
committed to a public repository -- which has already happened once in this
project, with the write-ahead log.

So the test that matters most is not "it round-trips". It is that the plaintext
cannot be found anywhere in the file.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.db.models import Claim, ClaimStatus, EligibilityCheck, Passenger
from app.db.session import create_all, create_db_engine, create_session_factory
from app.db.types import (
    EncryptedText,
    SecretsUnavailable,
    configure_cipher,
    reset_cipher_cache,
)
from tests.conftest import TEST_ENCRYPTION_KEY

ID_NUMBER = "312345678"


@pytest.fixture
def on_disk(tmp_path: Path):  # type: ignore[no-untyped-def]
    """A real database in a real file, because the file is the threat."""
    path = tmp_path / "test.db"
    engine = create_db_engine(f"sqlite:///{path}")
    create_all(engine)
    return path, create_session_factory(engine)


def _store(session_factory, national_id: str | None) -> uuid.UUID:  # type: ignore[no-untyped-def]
    check = EligibilityCheck(
        flight_number="LY315", flight_date=date(2026, 9, 17), status="DECIDED",
        provider="test",
    )
    claim = Claim(
        reference="ABC123", check=check, status=ClaimStatus.DRAFT.value,
        contact_name="Noam Hasson", contact_email="noam@example.com",
    )
    passenger = Passenger(
        claim=claim, full_name="Noam Hasson", national_id=national_id
    )
    with session_factory() as session:
        session.add(passenger)
        session.commit()
        return passenger.id


# --- The point of the exercise -----------------------------------------------


def test_the_number_is_not_in_the_database_file(on_disk) -> None:  # type: ignore[no-untyped-def]
    """THE test.

    Everything else here is detail; this is the promise. Somebody who walks off
    with the file has nothing.
    """
    path, session_factory = on_disk
    _store(session_factory, ID_NUMBER)

    raw = path.read_bytes()
    assert ID_NUMBER.encode() not in raw, "the identity number is readable in the file"


def test_the_application_still_sees_the_number(on_disk) -> None:  # type: ignore[no-untyped-def]
    """Encryption that changed how the rest of the code works would have been
    rewritten around, eventually, by somebody in a hurry."""
    path, session_factory = on_disk
    passenger_id = _store(session_factory, ID_NUMBER)

    with session_factory() as session:
        stored = session.get(Passenger, passenger_id)
        assert stored is not None
        assert stored.national_id == ID_NUMBER


def test_what_the_column_actually_holds(on_disk) -> None:  # type: ignore[no-untyped-def]
    """Read past the ORM to see the bytes, so this cannot pass by accident if
    the type decorator is removed."""
    path, session_factory = on_disk
    _store(session_factory, ID_NUMBER)

    with session_factory() as session:
        raw = session.execute(text("SELECT national_id FROM passengers")).scalar_one()

    assert raw != ID_NUMBER
    assert raw.startswith("gAAAAA"), "not a Fernet token"
    assert len(raw) > len(ID_NUMBER) * 5, "suspiciously short for a Fernet token"


def test_two_passengers_with_the_same_number_look_different(on_disk) -> None:  # type: ignore[no-untyped-def]
    """Fernet includes a random IV, so identical inputs give different
    ciphertext.

    Without that, anyone with the file could tell that two claims name the same
    person -- and could confirm a guessed number by encrypting it and looking
    for a match.
    """
    path, session_factory = on_disk
    type_ = EncryptedText()
    first = type_.process_bind_param(ID_NUMBER, None)
    second = type_.process_bind_param(ID_NUMBER, None)

    assert first != second
    assert type_.process_result_value(first, None) == ID_NUMBER
    assert type_.process_result_value(second, None) == ID_NUMBER


def test_nothing_to_store_stores_nothing(on_disk) -> None:  # type: ignore[no-untyped-def]
    """A passenger without an identity number is ordinary -- a minor, or
    somebody who has not supplied it yet -- and must not become ciphertext of
    the empty string."""
    path, session_factory = on_disk
    passenger_id = _store(session_factory, None)

    with session_factory() as session:
        assert session.get(Passenger, passenger_id).national_id is None  # type: ignore[union-attr]


# --- When the key is wrong or missing ----------------------------------------


def test_no_key_refuses_to_write_rather_than_storing_plaintext() -> None:
    """The single most important decision in the design.

    A fallback to plaintext is how sensitive data reaches production
    unencrypted and nobody notices for a year. Refusing turns a
    misconfiguration into a deploy failure instead of a quiet one.
    """
    configure_cipher("")
    try:
        with pytest.raises(SecretsUnavailable, match="ENCRYPTION_KEYS"):
            EncryptedText().process_bind_param(ID_NUMBER, None)
    finally:
        configure_cipher(TEST_ENCRYPTION_KEY)


def test_a_tampered_value_fails_loudly(on_disk) -> None:  # type: ignore[no-untyped-def]
    """Fernet is authenticated, so an edited ciphertext cannot decrypt to a
    different number.

    For an identity document, a value that is wrong in an undetectable way is
    worse than one that is missing: it would be copied onto a claim letter and
    sent to an airline.
    """
    path, session_factory = on_disk
    _store(session_factory, ID_NUMBER)

    with session_factory() as session:
        session.execute(
            text("UPDATE passengers SET national_id = :v"),
            {"v": "gAAAAAB" + "x" * 100},
        )
        session.commit()

    with session_factory() as session, pytest.raises(SecretsUnavailable):
        session.scalars(select(Passenger)).all()


def test_a_value_written_under_another_key_is_not_silently_returned() -> None:
    """A rotation done without re-encrypting, or a restored backup from a
    different deployment. Either way the ciphertext must not be handed back as
    though it were the number."""
    other_key = "rAOSXOQ4YMIlWEQnhfqKYb-nErNmYsjKp1mtNdOJcLk="
    configure_cipher(other_key)
    foreign = EncryptedText().process_bind_param(ID_NUMBER, None)

    configure_cipher(TEST_ENCRYPTION_KEY)
    with pytest.raises(SecretsUnavailable):
        EncryptedText().process_result_value(foreign, None)


# --- Rotation ----------------------------------------------------------------


def test_an_old_key_still_decrypts_while_a_new_one_encrypts() -> None:
    """What makes rotation possible without stopping the world.

    Put the new key first and keep the old one after it: writes use the new
    key, reads accept both, and re-encryption can happen at leisure.
    """
    old = TEST_ENCRYPTION_KEY
    new = "rAOSXOQ4YMIlWEQnhfqKYb-nErNmYsjKp1mtNdOJcLk="

    configure_cipher(old)
    written_with_old = EncryptedText().process_bind_param(ID_NUMBER, None)

    configure_cipher(f"{new},{old}")
    type_ = EncryptedText()
    assert type_.process_result_value(written_with_old, None) == ID_NUMBER

    written_now = type_.process_bind_param(ID_NUMBER, None)
    configure_cipher(new)
    assert EncryptedText().process_result_value(written_now, None) == ID_NUMBER, (
        "the new key did not encrypt; rotation would not finish"
    )

    configure_cipher(TEST_ENCRYPTION_KEY)


def test_a_nonsense_key_is_reported_as_such() -> None:
    """Rather than as a decryption failure, which sends whoever is on call
    looking for corrupted data instead of a typo in a deploy variable."""
    configure_cipher("not-a-real-key")
    try:
        with pytest.raises(SecretsUnavailable, match="not a valid Fernet key"):
            EncryptedText().process_bind_param(ID_NUMBER, None)
    finally:
        configure_cipher(TEST_ENCRYPTION_KEY)
        reset_cipher_cache()
