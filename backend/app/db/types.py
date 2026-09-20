"""Column types that keep the guarantees the domain relies on.

SQLite has no decimal type and no timezone-aware datetime type. Left alone it
will happily hand back a float where a Decimal went in, and a naive datetime
where an aware one went in -- quietly undoing two of the invariants the whole
system is built on.

These two types close both holes at the storage boundary, which is also where
the equivalent problems appear on PostgreSQL if this ever moves.

`EncryptedText` is here for a different reason: an identity document must not
be readable by anyone who obtains the database file. Putting it in the column
type means nothing above this layer has to remember to encrypt.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


class MoneyAmount(TypeDecorator[Decimal]):
    """An exact monetary amount, stored as an integer number of minor units.

    Storing 520.00 as a float would be the same mistake `Money` exists to
    prevent, one layer down. Storing it as the integer 52000 is exact, sorts
    correctly in SQL, and needs no dialect-specific decimal support.

    All three currencies here -- euro, pound, shekel -- have 100 minor units, so
    a single scale works for every one.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> int | None:
        if value is None:
            return None
        return int(value.scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))

    def process_result_value(
        self, value: int | None, dialect: Dialect
    ) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(Decimal("0.01"))


class UtcDateTime(TypeDecorator[datetime]):
    """A timezone-aware timestamp that is still timezone-aware on the way back.

    SQLite discards the offset, so a datetime written as 12:00+03:00 returns as
    naive 09:00 -- and a naive timestamp compared against an aware one raises,
    while two naive ones from different zones silently give a wrong answer.
    That is precisely the bug `FlightFacts` refuses to allow.

    So: convert to UTC going in, reattach UTC coming out. Everything in the
    database is UTC by construction.
    """

    # timezone=True so PostgreSQL uses `timestamptz` rather than a naive
    # `timestamp`. The conversion below makes the Python side correct either
    # way, but a naive column is a trap for everything that is not this
    # application: somebody querying with psql sees a time with no zone, and
    # any other writer can put local time in it. On SQLite it changes nothing,
    # because SQLite has no timestamp type to change.
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                f"refusing to store the naive timestamp {value!r}; "
                "timestamps must be timezone-aware"
            )
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def utc_now() -> datetime:
    """Default for created_at. A function, not `datetime.now(UTC)` evaluated at
    import time, which would stamp every row with the moment the process
    started."""
    return datetime.now(UTC)


def jsonable(value: Any) -> Any:
    """Make domain objects storable in a JSON column.

    Dates, datetimes, Decimals and enums all need a representation that survives
    a round trip through JSON without becoming something else.
    """
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value") and hasattr(value, "name"):
        return value.value
    return value


class SecretsUnavailable(RuntimeError):
    """No usable encryption key, so nothing sensitive may be read or written.

    Its own type because the two ways to get here need different fixes: an
    unset variable is a deployment that has not been finished, and an
    unreadable key is a deployment that has lost its data.
    """


_configured_keys: str | None = None


def configure_cipher(keys: str | None) -> None:
    """Hand the process its key, from settings rather than the raw environment.

    Called once wherever the database is set up, which is the one place every
    entry point -- the API, the archive, the enrichment job -- already goes
    through. A column type is constructed at import time and cannot be given a
    dependency, so the key has to be process-wide; this at least makes the
    handover explicit and testable instead of an implicit environment read.
    """
    global _configured_keys
    _configured_keys = keys
    _cipher.cache_clear()


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    """The key, resolved once.

    From configuration or the environment, never from a column: a key stored
    beside the data it protects is decoration. Read through `lru_cache`
    because it is process-wide by nature, which is also what a key is.

    ENCRYPTION_KEYS may hold several, comma-separated. The FIRST encrypts;
    every one can decrypt. That is what makes rotation possible without a
    stop-the-world migration: add the new key at the front, let writes use it,
    re-encrypt at leisure, then drop the old one.
    """
    # None means nobody configured this process, so the environment is the
    # source. An empty STRING means somebody configured it with nothing, which
    # is a deployment missing its key -- falling back to the environment there
    # would let a stray shell variable quietly supply one.
    raw = (
        os.environ.get("ENCRYPTION_KEYS", "")
        if _configured_keys is None
        else _configured_keys
    ).strip()
    if not raw:
        raise SecretsUnavailable(
            "ENCRYPTION_KEYS is not set, so identity documents cannot be read "
            "or written. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"'
        )
    try:
        keys = [Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()]
    except (ValueError, TypeError) as exc:
        raise SecretsUnavailable(
            f"ENCRYPTION_KEYS is not a valid Fernet key: {exc}"
        ) from exc
    if not keys:
        raise SecretsUnavailable("ENCRYPTION_KEYS contained no keys")
    return MultiFernet(keys)


def reset_cipher_cache() -> None:
    """Forget the cached key. For tests, and for a process that rotates keys."""
    _cipher.cache_clear()


class EncryptedText(TypeDecorator[str]):
    """Text that is encrypted on the way in and decrypted on the way out.

    Here, at the storage boundary, rather than at the call sites, for the same
    reason the write log is a listener rather than a line in each repository:
    nothing above this layer has to remember. A route reads
    `passenger.national_id` and gets the number; the database holds ciphertext
    and has never held anything else.

    WHAT THIS PROTECTS AGAINST
    --------------------------
    Somebody reading the database file. A stolen laptop, a copied backup, a
    misconfigured bucket, an operator browsing tables in DB Browser, or this
    file being committed to a public repository -- which has already happened
    once in this project's history, with the WAL.

    It does NOT protect a running application from itself. Anything that can
    query the database through this type sees plaintext, because that is the
    point. Access control is a separate problem and this is not it.

    AUTHENTICATED, NOT MERELY ENCRYPTED
    -----------------------------------
    Fernet carries an HMAC, so an altered ciphertext fails loudly instead of
    decrypting to a different number. For an identity document, a value that is
    wrong in an undetectable way is worse than one that is missing.

    THE PRICE
    ---------
    This column can no longer be searched, compared or indexed -- every row
    encrypts differently, by design, so `WHERE national_id = ?` finds nothing.
    That is affordable here only because nothing ever does that: the number is
    written once with a claim and read back with it. A system that needed to
    look somebody up by it would need a blind index instead, which is a much
    larger decision.

    And losing the key loses the data. That is the design working as intended,
    and it means the key needs a backup somewhere the database is not.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"expected str, got {type(value).__name__}")
        # No plaintext fallback when the key is missing. A fallback is exactly
        # how sensitive data reaches production unencrypted and nobody notices
        # for a year; refusing the write makes the misconfiguration a deploy
        # failure instead of a quiet one.
        return _cipher().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        try:
            return _cipher().decrypt(value.encode()).decode()
        except InvalidToken as exc:
            # Either the row predates encryption, or it was written with a key
            # we no longer hold, or it has been tampered with. All three are
            # somebody's problem to look at, and none of them may be papered
            # over by returning the ciphertext as though it were a number.
            raise SecretsUnavailable(
                "a stored value could not be decrypted: the key may have been "
                "rotated without re-encrypting, or the row may predate "
                "encryption"
            ) from exc
