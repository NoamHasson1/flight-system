"""Timestamps carry their timezone on PostgreSQL

Converts every UtcDateTime column from `timestamp` to `timestamptz`.

The application was already correct either way -- the column type converts to
UTC going in and reattaches UTC coming out -- but a naive column is a trap for
everything that is NOT this application. Somebody querying with psql sees a
time with no zone and no way to know what it means; any other writer can put
local time in it; and a report written in Tel Aviv and one written in London
silently disagree.

Existing values ARE UTC, which is what `AT TIME ZONE 'UTC'` asserts. Without
that clause PostgreSQL would interpret them in the server's timezone, which on
a machine set to Asia/Jerusalem would move every timestamp by three hours --
quietly, and in a direction that changes which side of a compensation
threshold a flight falls on.

A no-op on SQLite, which has no timestamp type to convert.


Revision ID: 68f6a7e7bfc1
Revises: a85191c922df
Create Date: 2026-09-20 11:34:05.067546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Our custom column types (MoneyAmount, UtcDateTime) are rendered by
# autogenerate as `app.db.types.X()`, but Alembic does not add the import that
# makes that name resolve. Without this line every generated migration fails
# with NameError on first run. Imported unconditionally because a migration
# that does not use it costs nothing.
import app.db.types


# revision identifiers, used by Alembic.
revision: str = '68f6a7e7bfc1'
down_revision: Union[str, Sequence[str], None] = 'a85191c922df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every column declared as UtcDateTime in app/db/models.py.
_COLUMNS = (
    ("eligibility_checks", "created_at"),
    ("claims", "created_at"),
    ("claims", "updated_at"),
    ("claims", "submitted_at"),
    ("claims", "confirmation_sent_at"),
    ("passengers", "created_at"),
    ("expenses", "created_at"),
    ("documents", "created_at"),
    ("flight_lookups", "observed_at"),
)


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN {column} '
            f'TYPE TIMESTAMPTZ USING {column} AT TIME ZONE \'UTC\''
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column in _COLUMNS:
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN {column} '
            f'TYPE TIMESTAMP USING {column} AT TIME ZONE \'UTC\''
        )
