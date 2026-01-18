"""Initial schema with all tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create project table
    op.create_table(
        'project',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('repository_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('documentation_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('github_owner', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('github_repo', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('github_stars', sa.Integer(), nullable=True),
        sa.Column('github_language', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_name'), 'project', ['name'], unique=True)
    
    # Create documentsection table
    op.create_table(
        'documentsection',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('level', sa.Enum('SUMMARY', 'OVERVIEW', 'DETAILED', 'TECHNICAL', name='documentationlevel'), nullable=False),
        sa.Column('section_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('source_file', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documentsection_project_id'), 'documentsection', ['project_id'], unique=False)
    
    # Create project_component table
    op.create_table(
        'project_component',
        sa.Column('parent_id', sa.Integer(), nullable=False),
        sa.Column('child_id', sa.Integer(), nullable=False),
        sa.Column('relationship_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['child_id'], ['project.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('parent_id', 'child_id'),
    )
    
    # Create project_contributor table
    op.create_table(
        'project_contributor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('avatar_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('contributions', sa.Integer(), nullable=False),
        sa.Column('profile_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_contributor_project_id'), 'project_contributor', ['project_id'], unique=False)
    
    # Create project_issue table
    op.create_table(
        'project_issue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('issue_number', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('state', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('author', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('labels', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('issue_created_at', sa.DateTime(), nullable=True),
        sa.Column('issue_updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_issue_project_id'), 'project_issue', ['project_id'], unique=False)
    
    # Create project_language table
    op.create_table(
        'project_language',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('language', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('bytes_count', sa.Integer(), nullable=False),
        sa.Column('percentage', sa.Float(), nullable=False),
        sa.Column('file_extensions', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('encoding', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_language_project_id'), 'project_language', ['project_id'], unique=False)
    
    # Create project_branch table
    op.create_table(
        'project_branch',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('is_protected', sa.Boolean(), nullable=False),
        sa.Column('commit_sha', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('commit_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('commit_author', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('commit_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_branch_project_id'), 'project_branch', ['project_id'], unique=False)
    
    # Create project_dependency table
    op.create_table(
        'project_dependency',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('version_spec', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('dep_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_dependency_project_id'), 'project_dependency', ['project_id'], unique=False)
    
    # Create project_pull_request table
    op.create_table(
        'project_pull_request',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('pr_number', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('state', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('author', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('base_branch', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('head_branch', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('is_draft', sa.Boolean(), nullable=False),
        sa.Column('is_merged', sa.Boolean(), nullable=False),
        sa.Column('additions', sa.Integer(), nullable=False),
        sa.Column('deletions', sa.Integer(), nullable=False),
        sa.Column('labels', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('pr_created_at', sa.DateTime(), nullable=True),
        sa.Column('pr_updated_at', sa.DateTime(), nullable=True),
        sa.Column('pr_merged_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_pull_request_project_id'), 'project_pull_request', ['project_id'], unique=False)
    
    # Create project_release table
    op.create_table(
        'project_release',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('tag_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('body', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('is_prerelease', sa.Boolean(), nullable=False),
        sa.Column('is_draft', sa.Boolean(), nullable=False),
        sa.Column('author', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('target_commitish', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('release_created_at', sa.DateTime(), nullable=True),
        sa.Column('release_published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_release_project_id'), 'project_release', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_project_release_project_id'), table_name='project_release')
    op.drop_table('project_release')
    op.drop_index(op.f('ix_project_pull_request_project_id'), table_name='project_pull_request')
    op.drop_table('project_pull_request')
    op.drop_index(op.f('ix_project_dependency_project_id'), table_name='project_dependency')
    op.drop_table('project_dependency')
    op.drop_index(op.f('ix_project_branch_project_id'), table_name='project_branch')
    op.drop_table('project_branch')
    op.drop_index(op.f('ix_project_language_project_id'), table_name='project_language')
    op.drop_table('project_language')
    op.drop_index(op.f('ix_project_issue_project_id'), table_name='project_issue')
    op.drop_table('project_issue')
    op.drop_index(op.f('ix_project_contributor_project_id'), table_name='project_contributor')
    op.drop_table('project_contributor')
    op.drop_table('project_component')
    op.drop_index(op.f('ix_documentsection_project_id'), table_name='documentsection')
    op.drop_table('documentsection')
    op.drop_index(op.f('ix_project_name'), table_name='project')
    op.drop_table('project')
