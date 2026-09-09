"""Temporary public-demo visitor accounts (ADR-051).

Revision ID: b7d2e8f4a1c9
Revises: f4b82d903e61
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e8f4a1c9"
down_revision: str | Sequence[str] | None = "f4b82d903e61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_visitors",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subject_hash", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("scrubbed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_demo_visitors_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_demo_visitors")),
    )
    op.create_index(
        op.f("ix_demo_visitors_subject_hash"),
        "demo_visitors",
        ["subject_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_demo_visitors_subject_hash"), table_name="demo_visitors")
    op.drop_table("demo_visitors")
