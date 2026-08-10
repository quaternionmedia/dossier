"""Add the governance read-model tables.

Revision ID: 005_governance
Revises: 004_full_name
Create Date: 2026-08-09

Holds what the corpus's generated documents report. Deliberately not linked to
`project.id`: `dossier github sync` empties and rebuilds the project tables on
every run, and governance state hung off them would vanish at the next sync.
The join is the repository name.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '005_governance'
down_revision: Union[str, None] = '004_full_name'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'governance_repository',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        # Per source, not merged: the two documents fail independently, and
        # "never read" must stay distinguishable from "reports nothing".
        sa.Column('governance_generated_at', sa.DateTime(), nullable=True),
        sa.Column('harness_generated_at', sa.DateTime(), nullable=True),
        sa.Column('governance_observed_at', sa.DateTime(), nullable=True),
        sa.Column('harness_staleness_budget_hours', sa.Float(), nullable=True),
        sa.Column('loaded_at', sa.DateTime(), nullable=False),
        sa.Column('branch_ref', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('branch_commit', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        # Each measurable fact is a pair: the value, and the reason nobody
        # could establish it. Both null means the document stated a real null.
        sa.Column('behind_corpus', sa.Integer(), nullable=True),
        sa.Column('behind_corpus_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('ahead_of_corpus', sa.Integer(), nullable=True),
        sa.Column('ahead_of_corpus_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('last_propagation', sa.DateTime(), nullable=True),
        sa.Column('last_propagation_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('seed_drift', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('seed_drift_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('records_total', sa.Integer(), nullable=True),
        sa.Column('records_ratified', sa.Integer(), nullable=True),
        sa.Column('open_prs_count', sa.Integer(), nullable=True),
        sa.Column('open_prs_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('phase', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('phase_source', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('precondition', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('precondition_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('precondition_missing', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('slot_state', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('slot_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('slot_open_prs', sa.Integer(), nullable=True),
        sa.Column('slot_violations', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_governance_repository_name'),
        'governance_repository',
        ['name'],
        unique=True,
    )

    op.create_table(
        'governance_thread',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('stage', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('pr', sa.Integer(), nullable=True),
        sa.Column('base', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('author', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('additions', sa.Integer(), nullable=True),
        sa.Column('deletions', sa.Integer(), nullable=True),
        sa.Column('commits', sa.Integer(), nullable=True),
        sa.Column('changed_files', sa.Integer(), nullable=True),
        sa.Column('mergeable_state', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('thread_updated_at', sa.DateTime(), nullable=True),
        sa.Column('idle_hours', sa.Float(), nullable=True),
        sa.Column('stalled', sa.Boolean(), nullable=False),
        sa.Column('source_generated_at', sa.DateTime(), nullable=True),
        sa.Column('loaded_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_governance_thread_repository_name'),
        'governance_thread',
        ['repository_name'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_governance_thread_repository_name'), table_name='governance_thread')
    op.drop_table('governance_thread')
    op.drop_index(op.f('ix_governance_repository_name'), table_name='governance_repository')
    op.drop_table('governance_repository')
