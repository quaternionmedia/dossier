"""Add the release layer to the governance read model.

Revision ID: 008_release
Revises: 007_reclaim
Create Date: 2026-08-11

`main` is readiness; a `v` tag is governance passed. The corpus's harness
document now carries a `release` layer per repository, and these columns hold
it: the state, the latest tag, whether that tag is annotated, and how many
commits the default branch carries beyond it.

Stored as a value plus an `unknown` reason, like every other measurable fact
here. A repository whose tags could not be read must not render like one that
has none.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '008_release'
down_revision: Union[str, None] = '007_reclaim'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = (
    ('release_state', sqlmodel.sql.sqltypes.AutoString()),
    ('release_unknown', sqlmodel.sql.sqltypes.AutoString()),
    ('release_latest', sqlmodel.sql.sqltypes.AutoString()),
    ('release_annotated', sa.Boolean()),
    ('release_unreleased_commits', sa.Integer()),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column('governance_repository', sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column('governance_repository', name)
