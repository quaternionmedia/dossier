"""Add delta tables for tracking project changes.

Revision ID: 005_delta_tables
Revises: 004_full_name
Create Date: 2026-01-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "005_delta_tables"
down_revision: Union[str, None] = "004_full_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create project_delta table
    op.create_table(
        "project_delta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("phase", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("phase_changed_at", sa.DateTime(), nullable=False),
        sa.Column("priority", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("delta_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("branch_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_delta_project_id"), "project_delta", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_delta_phase"), "project_delta", ["phase"], unique=False
    )

    # Create delta_note table
    op.create_table(
        "delta_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delta_id", sa.Integer(), nullable=False),
        sa.Column("phase", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["delta_id"],
            ["project_delta.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_delta_note_delta_id"), "delta_note", ["delta_id"], unique=False
    )

    # Create delta_link table
    op.create_table(
        "delta_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("delta_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["delta_id"],
            ["project_delta.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_delta_link_delta_id"), "delta_link", ["delta_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_delta_link_delta_id"), table_name="delta_link")
    op.drop_table("delta_link")
    op.drop_index(op.f("ix_delta_note_delta_id"), table_name="delta_note")
    op.drop_table("delta_note")
    op.drop_index(op.f("ix_project_delta_phase"), table_name="project_delta")
    op.drop_index(op.f("ix_project_delta_project_id"), table_name="project_delta")
    op.drop_table("project_delta")
