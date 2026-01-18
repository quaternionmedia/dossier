"""Add performance indexes

Revision ID: 003_perf_indexes
Revises: 002_project_version
Create Date: 2026-01-18

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '003_perf_indexes'
down_revision: Union[str, None] = '002_project_version'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    """Check if an index already exists."""
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def _safe_create_index(inspector, index_name: str, table_name: str, columns: list, unique: bool = False):
    """Create an index only if it doesn't already exist."""
    if not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # Add indexes to project_component for faster parent/child lookups
    _safe_create_index(inspector, 'ix_project_component_parent_id', 'project_component', ['parent_id'])
    _safe_create_index(inspector, 'ix_project_component_child_id', 'project_component', ['child_id'])
    
    # Add composite indexes for common filter/sort patterns on project table
    _safe_create_index(inspector, 'ix_project_stars_name', 'project', ['github_stars', 'name'])
    _safe_create_index(inspector, 'ix_project_synced_name', 'project', ['last_synced_at', 'name'])
    _safe_create_index(inspector, 'ix_project_language', 'project', ['github_language'])
    
    # Add index for project_version table
    if 'project_version' in inspector.get_table_names():
        _safe_create_index(inspector, 'ix_project_version_project_id', 'project_version', ['project_id'])
        _safe_create_index(inspector, 'ix_project_version_semver', 'project_version', ['project_id', 'major', 'minor', 'patch'])


def downgrade() -> None:
    # Try to drop version indexes if they exist
    try:
        op.drop_index('ix_project_version_semver', table_name='project_version')
        op.drop_index('ix_project_version_project_id', table_name='project_version')
    except Exception:
        pass  # Table may not exist
    
    op.drop_index('ix_project_language', table_name='project')
    op.drop_index('ix_project_synced_name', table_name='project')
    op.drop_index('ix_project_stars_name', table_name='project')
    op.drop_index('ix_project_component_child_id', table_name='project_component')
    op.drop_index('ix_project_component_parent_id', table_name='project_component')
