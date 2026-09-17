"""The eligibility_checks table.

Every check a customer runs is recorded here, eligible or not.

Generated with autogenerate against an EMPTY database. Pointing it at a
database that already had the table -- which is what happens if you forget to
set DATABASE_URL -- produces a migration containing `pass`, and a fresh deploy
then creates no schema at all.


Revision ID: 4cfc08cbc8f0
Revises: 
Create Date: 2026-09-17 11:30:37.909274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.db.types


# revision identifiers, used by Alembic.
revision: str = '4cfc08cbc8f0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('eligibility_checks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', app.db.types.UtcDateTime(), nullable=False),
    sa.Column('flight_number', sa.String(length=10), nullable=False),
    sa.Column('flight_date', sa.Date(), nullable=False),
    sa.Column('contact_name', sa.String(length=200), nullable=True),
    sa.Column('contact_email', sa.String(length=320), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('verdict', sa.String(length=20), nullable=True),
    sa.Column('message', sa.String(length=2000), nullable=True),
    sa.Column('best_regulation', sa.String(length=20), nullable=True),
    sa.Column('best_amount', app.db.types.MoneyAmount(), nullable=True),
    sa.Column('best_currency', sa.String(length=3), nullable=True),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('flight_snapshot', sa.JSON(), nullable=True),
    sa.Column('result_detail', sa.JSON(), nullable=True),
    sa.Column('provider_payload', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('eligibility_checks', schema=None) as batch_op:
        batch_op.create_index('ix_checks_flight', ['flight_number', 'flight_date'], unique=False)
        batch_op.create_index('ix_checks_review_queue', ['verdict', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_eligibility_checks_contact_email'), ['contact_email'], unique=False)
        batch_op.create_index(batch_op.f('ix_eligibility_checks_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_eligibility_checks_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_eligibility_checks_verdict'), ['verdict'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('eligibility_checks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_eligibility_checks_verdict'))
        batch_op.drop_index(batch_op.f('ix_eligibility_checks_status'))
        batch_op.drop_index(batch_op.f('ix_eligibility_checks_created_at'))
        batch_op.drop_index(batch_op.f('ix_eligibility_checks_contact_email'))
        batch_op.drop_index('ix_checks_review_queue')
        batch_op.drop_index('ix_checks_flight')

    op.drop_table('eligibility_checks')
