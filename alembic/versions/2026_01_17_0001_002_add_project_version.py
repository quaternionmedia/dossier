"""Add project_version table for semver tracking

Revision ID: 002_project_version
Revises: 001_initial
Create Date: 2026-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '002_project_version'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create project_version table
    op.create_table(
        'project_version',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('version', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('major', sa.Integer(), nullable=False),
        sa.Column('minor', sa.Integer(), nullable=False),
        sa.Column('patch', sa.Integer(), nullable=False),
        sa.Column('prerelease', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('build_metadata', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('release_id', sa.Integer(), nullable=True),
        sa.Column('is_latest', sa.Boolean(), nullable=False),
        sa.Column('release_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('changelog_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('release_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.ForeignKeyConstraint(['release_id'], ['project_release.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_version_project_id'), 'project_version', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_project_version_project_id'), table_name='project_version')
    op.drop_table('project_version')
