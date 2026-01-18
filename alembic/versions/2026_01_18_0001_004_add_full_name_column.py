"""Add full_name column to project table.

Revision ID: 004_full_name
Revises: 003_perf_indexes
Create Date: 2026-01-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_full_name'
down_revision: Union[str, None] = '003_perf_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add full_name column (nullable since existing rows won't have it)
    op.add_column('project', sa.Column('full_name', sa.String(), nullable=True))
    
    # Create index for faster lookups
    op.create_index('ix_project_full_name', 'project', ['full_name'])
    
    # Populate full_name from existing data
    # Use github_owner/github_repo if available, otherwise use name
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE project 
        SET full_name = CASE 
            WHEN github_owner IS NOT NULL AND github_repo IS NOT NULL 
            THEN github_owner || '/' || github_repo
            ELSE name
        END
        WHERE full_name IS NULL
    """))


def downgrade() -> None:
    op.drop_index('ix_project_full_name', table_name='project')
    op.drop_column('project', 'full_name')
