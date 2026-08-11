"""Add the disk read-model tables.

Revision ID: 006_disk
Revises: 005_governance
Create Date: 2026-08-11

Holds what the corpus's `ci/disk_status.py` reports, one snapshot per reading.
Unlike the governance tables these are append-only: the question worth asking
of a disk is what grew since last time, and no single reading can answer it.

Not linked to `project.id`, for the reason 005 gives -- `dossier github sync`
rebuilds the project tables on every run -- and additionally because a disk
belongs to a machine and not to a project. `disk_snapshot.machine` carries
that scope in the row rather than implying it from where the store sits, so a
store copied between machines stays readable instead of merging two histories
into one misleading trend.

The child tables cascade from `disk_snapshot.id`, so pruning old snapshots is
a delete of the parent rows.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '006_disk'
down_revision: Union[str, None] = '005_governance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'disk_snapshot',
        sa.Column('id', sa.Integer(), nullable=False),
        # The scope, in the row. A store is a file somebody can copy, which is
        # a weaker boundary than the repository the corpus generator refuses
        # to write into.
        sa.Column('machine', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # The document's own timestamp, never the load's: a snapshot loaded
        # today from last week's document describes last week.
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('loaded_at', sa.DateTime(), nullable=False),
        sa.Column('staleness_budget_hours', sa.Float(), nullable=True),
        sa.Column('policy_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('tool', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('volumes_critical', sa.Integer(), nullable=True),
        sa.Column('volumes_warn', sa.Integer(), nullable=True),
        sa.Column('volumes_unknown', sa.Integer(), nullable=True),
        sa.Column('targets_measured', sa.Integer(), nullable=True),
        sa.Column('targets_unknown', sa.Integer(), nullable=True),
        sa.Column('reclaimable_refetched', sa.Integer(), nullable=True),
        sa.Column('reclaimable_rebuilt', sa.Integer(), nullable=True),
        sa.Column('reclaimable_destructive', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_disk_snapshot_machine'), 'disk_snapshot', ['machine'], unique=False
    )
    # The delta query orders by this and takes two rows, so it is the one
    # index that stops a long history costing a scan.
    op.create_index(
        op.f('ix_disk_snapshot_generated_at'),
        'disk_snapshot',
        ['generated_at'],
        unique=False,
    )

    op.create_table(
        'disk_volume',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # A pair, as everywhere: the measured fact, or the reason nobody could
        # establish it. A volume nobody could read is not a volume with room.
        sa.Column('total_bytes', sa.Integer(), nullable=True),
        sa.Column('used_bytes', sa.Integer(), nullable=True),
        sa.Column('free_bytes', sa.Integer(), nullable=True),
        sa.Column('free_ratio', sa.Float(), nullable=True),
        sa.Column('usage_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('state', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('severity', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('thresholds_fired', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['disk_snapshot.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_disk_volume_snapshot_id'), 'disk_volume', ['snapshot_id'], unique=False
    )
    op.create_index(op.f('ix_disk_volume_path'), 'disk_volume', ['path'], unique=False)

    op.create_table(
        'disk_target',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('safety', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('owner', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        # The pair the delta turns on. Subtracting a measured value from an
        # unmeasured one produces a confident, specific, wrong claim that
        # something was reclaimed, so both columns travel together.
        sa.Column('bytes', sa.Integer(), nullable=True),
        sa.Column('bytes_unknown', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('files', sa.Integer(), nullable=True),
        sa.Column('units_total', sa.Integer(), nullable=True),
        sa.Column('unreadable', sa.Integer(), nullable=True),
        sa.Column('largest_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('largest_bytes', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['snapshot_id'], ['disk_snapshot.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_disk_target_snapshot_id'), 'disk_target', ['snapshot_id'], unique=False
    )
    op.create_index(op.f('ix_disk_target_name'), 'disk_target', ['name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_disk_target_name'), table_name='disk_target')
    op.drop_index(op.f('ix_disk_target_snapshot_id'), table_name='disk_target')
    op.drop_table('disk_target')
    op.drop_index(op.f('ix_disk_volume_path'), table_name='disk_volume')
    op.drop_index(op.f('ix_disk_volume_snapshot_id'), table_name='disk_volume')
    op.drop_table('disk_volume')
    op.drop_index(op.f('ix_disk_snapshot_generated_at'), table_name='disk_snapshot')
    op.drop_index(op.f('ix_disk_snapshot_machine'), table_name='disk_snapshot')
    op.drop_table('disk_snapshot')
