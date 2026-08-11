"""Add the disk reclaim table: an action recorded as the pair of readings it sits between.

Revision ID: 007_reclaim
Revises: 006_disk
Create Date: 2026-08-11

A reclaim is a measurement, an action, and another measurement. Storing it as
two `disk_snapshot` ids rather than as its own kind of event means the change
it caused is computed by the same arithmetic as any observed change, carries
the same refusals, and composes with them.

`claimed_bytes` and `freed_bytes` are both kept because they are different
facts: the reclaimer reports what it removed, the volume reports what came
back, and they diverge for ordinary reasons -- a concurrent write, or space
freed inside a container disk that does not shrink. The gap between them is
only visible because both are stored.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '007_reclaim'
down_revision: Union[str, None] = '006_disk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'disk_reclaim',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('machine', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        # What was asked for, verbatim, so a row explains itself without the
        # shell history that produced it.
        sa.Column('allow', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('targets', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('applied', sa.Boolean(), nullable=False),
        # The pair. A null `after` is a dry run, or a run that died before its
        # second reading -- neither of which is a run that freed nothing.
        sa.Column('before_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('after_snapshot_id', sa.Integer(), nullable=True),
        # Two different facts: what the tool removed, and what the volume gave
        # back. Keeping only one would either claim space that never returned
        # or blame the tool for a concurrent download.
        sa.Column('claimed_bytes', sa.Integer(), nullable=True),
        sa.Column('claimed_paths', sa.Integer(), nullable=True),
        sa.Column('freed_bytes', sa.Integer(), nullable=True),
        sa.Column('freed_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('exit_status', sa.Integer(), nullable=True),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('output', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['before_snapshot_id'], ['disk_snapshot.id'], ),
        sa.ForeignKeyConstraint(['after_snapshot_id'], ['disk_snapshot.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_disk_reclaim_machine'), 'disk_reclaim', ['machine'], unique=False
    )
    op.create_index(
        op.f('ix_disk_reclaim_started_at'), 'disk_reclaim', ['started_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_disk_reclaim_started_at'), table_name='disk_reclaim')
    op.drop_index(op.f('ix_disk_reclaim_machine'), table_name='disk_reclaim')
    op.drop_table('disk_reclaim')
