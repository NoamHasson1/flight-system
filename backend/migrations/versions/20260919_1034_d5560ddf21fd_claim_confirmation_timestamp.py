"""Record when a claim's confirmation email was sent.

Its absence is what makes sending idempotent: a retried request or a replayed
background task cannot send the same confirmation twice.


Revision ID: d5560ddf21fd
Revises: f7739d9010e8
Create Date: 2026-09-19 10:34:29.834178

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
revision: str = 'd5560ddf21fd'
down_revision: Union[str, Sequence[str], None] = 'f7739d9010e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confirmation_sent_at', app.db.types.UtcDateTime(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_column('confirmation_sent_at')

