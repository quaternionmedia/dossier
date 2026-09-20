"""add is_private to project

A private repository's name is not this org's to publish, and the overview is
built to be shared. The column records the host's `private` field so the
overview can redact the name to a stable reference. NOT NULL with a server
default of false: the table already has rows, and an existing row whose
visibility was never synced reads false, which the overview treats
conservatively as public-until-known.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision = "c1f2a3b4d5e6"
down_revision: Union[str, None] = "b7c4d1a90e33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("is_private", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("project") as batch:
        batch.drop_column("is_private")
