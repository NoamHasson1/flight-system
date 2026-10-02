"""a booking reference can be longer than a PNR

Revision ID: b5a383c8cf61
Revises: 68f6a7e7bfc1
Create Date: 2026-10-02 15:19:11.755806

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
revision: str = 'b5a383c8cf61'
down_revision: Union[str, Sequence[str], None] = '68f6a7e7bfc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen booking_reference from 20 to 64 characters.

    Twenty was sized for an airline PNR, which is six characters. It is too
    short for an e-ticket number (13 digits) or an online travel agent's
    itinerary reference, and a real customer hit it while filling in the
    form -- learning about it three steps later, in English.

    Widening a varchar rewrites no data and loses nothing.

    Batch mode because the tests run this chain on SQLite, which has no
    ALTER COLUMN TYPE at all -- Alembic rebuilds the table instead. On
    PostgreSQL, where this actually runs, it is a plain ALTER.
    """
    with op.batch_alter_table("claims", schema=None) as batch_op:
        batch_op.alter_column(
            "booking_reference",
            existing_type=sa.String(length=20),
            type_=sa.String(length=64),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Narrow it back, which can LOSE DATA.

    Any reference longer than 20 characters -- the ones this migration
    exists to allow -- would be truncated or rejected. Spelled out rather
    than left as a silent `alter_column`, because a downgrade run against a
    populated database is how a claim quietly loses its reference.
    """
    with op.batch_alter_table("claims", schema=None) as batch_op:
        batch_op.alter_column(
            "booking_reference",
            existing_type=sa.String(length=64),
            type_=sa.String(length=20),
            existing_nullable=True,
        )
