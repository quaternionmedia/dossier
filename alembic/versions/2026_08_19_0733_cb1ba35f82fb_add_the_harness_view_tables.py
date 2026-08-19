"""add the harness view tables

Autogenerate also proposed eleven drops -- indexes and columns it could not see
declared. That is unrelated drift, and a migration that quietly removes an
index is one nobody can review, so only the two new tables are here.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = "cb1ba35f82fb"
down_revision: Union[str, None] = '4a0159a74bbe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('harness_invocation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('address', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('project', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tool_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('ran_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('loaded_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_harness_invocation_address'), 'harness_invocation', ['address'], unique=True)
    op.create_index(op.f('ix_harness_invocation_project'), 'harness_invocation', ['project'], unique=False)
    op.create_table('harness_snapshot',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('invocations', sa.Integer(), nullable=False),
    sa.Column('failures', sa.Integer(), nullable=False),
    sa.Column('human_requests', sa.Integer(), nullable=False),
    sa.Column('human_responses', sa.Integer(), nullable=False),
    sa.Column('database', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('loaded_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_harness_snapshot_project'), 'harness_snapshot', ['project'], unique=False)


def downgrade() -> None:
    op.drop_table("harness_snapshot")
    op.drop_table("harness_invocation")
