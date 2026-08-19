"""add is_fork and is_archived to project

Autogenerate also proposed dropping three indexes it could not see declared.
Those are unrelated drift and dropping them is not what this change is for, so
only the two columns are here -- a migration that quietly removes an index is a
migration nobody can review.

Both columns are NOT NULL with a server default: the table already has rows,
and a NOT NULL column added without one fails on every existing row.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision = "4a0159a74bbe"
down_revision: Union[str, None] = '009_delta_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("is_fork", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.drop_column("is_archived")
        batch.drop_column("is_fork")
