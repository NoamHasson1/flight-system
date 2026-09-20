"""Encrypt national identity numbers at rest

Converts `passengers.national_id` from plaintext to ciphertext in place, using
the key in ENCRYPTION_KEYS.

THIS MIGRATION NEEDS THE KEY. Without it the run stops before touching
anything, rather than half-converting a table: a column holding some plaintext
and some ciphertext cannot be read back by either code path.

A value that already looks encrypted is left alone, so re-running is safe.

THE DOWNGRADE IS DELIBERATELY REAL. Decrypting back to plaintext is a terrible
thing to do and exactly what somebody needs at 2am when a key is lost and the
alternative is losing the claims entirely. It refuses without the key, because
then there is nothing to go back to.


Revision ID: a85191c922df
Revises: 9d38e68ee9d4
Create Date: 2026-09-20 11:05:02.847312

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
revision: str = 'a85191c922df'
down_revision: Union[str, Sequence[str], None] = '9d38e68ee9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cipher():
    """The key, read here rather than through app code.

    A migration must keep working when the application around it has moved on,
    so it reads the environment directly instead of importing a module whose
    shape may have changed by the time somebody replays this from an empty
    database.
    """
    import os

    from cryptography.fernet import Fernet, MultiFernet

    raw = os.environ.get("ENCRYPTION_KEYS", "").strip()
    if not raw:
        raise RuntimeError(
            "ENCRYPTION_KEYS is not set. This migration converts identity "
            "numbers to ciphertext and cannot run without the key -- stopping "
            "now rather than leaving the column half-converted."
        )
    return MultiFernet([Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()])


def _looks_encrypted(value: str) -> bool:
    """Fernet tokens start with a version byte of 0x80, which base64-encodes to
    a leading "gAAAAA". An Israeli identity number does not."""
    return value.startswith("gAAAAA")


def upgrade() -> None:
    """Upgrade schema."""
    cipher = _cipher()

    # Widen the column FIRST. A Fernet token is about 120 characters against
    # the 40 this column allowed for an identity number -- SQLite would store
    # it anyway, since it does not enforce declared widths, and PostgreSQL
    # would refuse. Converting the data before the type would therefore work
    # here and fail on the database this is meant to move to.
    with op.batch_alter_table("passengers", schema=None) as batch_op:
        batch_op.alter_column(
            "national_id",
            existing_type=sa.String(length=40),
            type_=sa.Text(),
            existing_nullable=True,
        )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, national_id FROM passengers WHERE national_id IS NOT NULL")
    ).fetchall()

    converted = 0
    for row_id, value in rows:
        if not value or _looks_encrypted(value):
            continue
        connection.execute(
            sa.text("UPDATE passengers SET national_id = :v WHERE id = :id"),
            {"v": cipher.encrypt(value.encode()).decode(), "id": row_id},
        )
        converted += 1
    print(f"encrypted {converted} of {len(rows)} identity numbers")


def downgrade() -> None:
    """Downgrade schema."""
    cipher = _cipher()
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, national_id FROM passengers WHERE national_id IS NOT NULL")
    ).fetchall()

    for row_id, value in rows:
        if not value or not _looks_encrypted(value):
            continue
        connection.execute(
            sa.text("UPDATE passengers SET national_id = :v WHERE id = :id"),
            {"v": cipher.decrypt(value.encode()).decode(), "id": row_id},
        )

    # Narrow the column only after the ciphertext is gone, or the plaintext it
    # is being narrowed back around would not fit while the conversion runs.
    with op.batch_alter_table("passengers", schema=None) as batch_op:
        batch_op.alter_column(
            "national_id",
            existing_type=sa.Text(),
            type_=sa.String(length=40),
            existing_nullable=True,
        )
