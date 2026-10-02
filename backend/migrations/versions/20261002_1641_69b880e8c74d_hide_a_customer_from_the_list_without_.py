"""hide a customer from the list without destroying them

Revision ID: 69b880e8c74d
Revises: b5a383c8cf61
Create Date: 2026-10-02 16:41:32.577362

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
revision: str = '69b880e8c74d'
down_revision: Union[str, Sequence[str], None] = 'b5a383c8cf61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A customer can be removed from the operator's list, reversibly.

    The screen calls it "delete" because that is what the operator means.
    What it does is stamp this column, so the row -- and the claim
    evidence hanging off it -- survives a misclick and can be restored.

    Indexed because EVERY list query filters on it. An unindexed nullable
    column that appears in the default WHERE clause is a sequential scan on
    the busiest query in the application.
    """
    with op.batch_alter_table("eligibility_checks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("hidden_at", app.db.types.UtcDateTime(), nullable=True)
        )
        batch_op.create_index(
            "ix_eligibility_checks_hidden_at", ["hidden_at"], unique=False
        )


def downgrade() -> None:
    """Drops the column, which LOSES which rows were hidden.

    Harmless as data loss goes -- everything reappears in the list rather
    than vanishing -- but worth saying out loud rather than leaving as a
    bare `drop_column`.
    """
    with op.batch_alter_table("eligibility_checks", schema=None) as batch_op:
        batch_op.drop_index("ix_eligibility_checks_hidden_at")
        batch_op.drop_column("hidden_at")
