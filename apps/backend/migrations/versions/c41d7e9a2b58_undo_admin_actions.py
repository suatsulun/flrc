"""undoable admin actions (ADR-075)

Each undoable administrative write records what it changed and the snapshot
that restores the previous state. Rows expire after seven days.

Revision ID: c41d7e9a2b58
Revises: 9b3e5d7f1c20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c41d7e9a2b58"
down_revision: str | Sequence[str] | None = "9b3e5d7f1c20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("undo_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("undone_at", sa.DateTime(), nullable=True),
        sa.Column("undone_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_admin_actions_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by"],
            ["users.id"],
            name=op.f("fk_admin_actions_undone_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_actions")),
    )
    op.create_index(op.f("ix_admin_actions_expires_at"), "admin_actions", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_actions_expires_at"), table_name="admin_actions")
    op.drop_table("admin_actions")
