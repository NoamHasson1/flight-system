"""How much notice the passenger got, in buckets

Replaces `claims.cancellation_notice_days` (an integer) with
`claims.cancellation_notice` (a bucket).

A day count cannot express the two answers that decide the most claims. "The
airline never told me" and "I cannot remember" are not quantities, and an
integer column forces both into a NULL that reads exactly like "not asked yet".
A claim handler seeing NULL could not tell whether the passenger had answered.

The buckets are drawn around the fourteen-day boundary that both EC261 Article
5(1)(c) and the Israeli law use, so the plainly-payable and plainly-exempt
answers stay unambiguous and the two unquantifiable ones get names.

Existing day counts are carried across rather than dropped. Nothing that was
recorded is lost; the two new answers simply had no way of being recorded
before.

Revision ID: b17fa011c226
Revises: d5560ddf21fd
Create Date: 2026-09-19 13:31:49.468651

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
revision: str = 'b17fa011c226'
down_revision: Union[str, Sequence[str], None] = 'd5560ddf21fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('cancellation_notice', sa.String(length=20), nullable=True)
        )

    # Carried in its own statement rather than inside the batch: on SQLite a
    # batch operation rebuilds the table on exit, so an UPDATE in the middle
    # would be written to the copy that is about to be replaced.
    op.execute(
        """
        UPDATE claims SET cancellation_notice = CASE
            WHEN cancellation_notice_days IS NULL THEN NULL
            WHEN cancellation_notice_days = 0  THEN 'ON_THE_DAY'
            WHEN cancellation_notice_days < 7  THEN 'UNDER_A_WEEK'
            WHEN cancellation_notice_days < 14 THEN 'ONE_TO_TWO_WEEKS'
            ELSE 'OVER_TWO_WEEKS'
        END
        """
    )

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('cancellation_notice_days')


def downgrade() -> None:
    """Downgrade schema.

    Lossy, unavoidably: a bucket is a range, so it cannot become the exact day
    count it was built from. The midpoint of each range is written back, and
    the two answers that have no numeric equivalent -- never told, cannot
    remember -- become NULL, which is where they lived before this migration
    existed.
    """
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('cancellation_notice_days', sa.INTEGER(), nullable=True)
        )

    op.execute(
        """
        UPDATE claims SET cancellation_notice_days = CASE
            cancellation_notice
            WHEN 'ON_THE_DAY'       THEN 0
            WHEN 'UNDER_A_WEEK'     THEN 3
            WHEN 'ONE_TO_TWO_WEEKS' THEN 10
            WHEN 'OVER_TWO_WEEKS'   THEN 21
            ELSE NULL
        END
        """
    )

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('cancellation_notice')
