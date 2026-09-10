"""Teacher report names, PNG signatures, and administrative identity audit.

Revision ID: e2a91c743b60
Revises: b7d2e8f4a1c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2a91c743b60"
down_revision: str | Sequence[str] | None = "b7d2e8f4a1c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable additions preserve existing accounts and report-name fallback.
    op.add_column("users", sa.Column("report_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("signature_png", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("signature_digest", sa.String(), nullable=True))
    op.create_table(
        "report_identity_audits",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("before", postgresql.JSONB(), nullable=False),
        sa.Column("after", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_report_identity_audits_user_id", "report_identity_audits", ["user_id"])


def downgrade() -> None:
    op.drop_table("report_identity_audits")
    op.drop_column("users", "signature_digest")
    op.drop_column("users", "signature_png")
    op.drop_column("users", "report_name")
