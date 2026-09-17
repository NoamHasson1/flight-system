"""Column types that keep the guarantees the domain relies on.

SQLite has no decimal type and no timezone-aware datetime type. Left alone it
will happily hand back a float where a Decimal went in, and a naive datetime
where an aware one went in -- quietly undoing two of the invariants the whole
system is built on.

These two types close both holes at the storage boundary, which is also where
the equivalent problems appear on PostgreSQL if this ever moves.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import DateTime, Integer
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

    impl = DateTime
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
