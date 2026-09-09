"""durable job runs

Revision ID: 5e9c1e0f2a44
Revises: ed892699e61d
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5e9c1e0f2a44"
down_revision: str | Sequence[str] | None = "ed892699e61d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("output_filename", sa.String(), nullable=True),
        sa.Column("output_mime", sa.String(), nullable=True),
        sa.Column("output_size", sa.BigInteger(), nullable=True),
        sa.Column("output_blob", sa.LargeBinary(), nullable=True),
        sa.Column("output_expires_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('progress_pdf','german_karne','french_karne','year_export')",
            name=op.f("ck_job_runs_kind_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')",
            name=op.f("ck_job_runs_status_valid"),
        ),
        sa.CheckConstraint("progress >= 0", name=op.f("ck_job_runs_progress_nonnegative")),
        sa.CheckConstraint("total >= 0", name=op.f("ck_job_runs_total_nonnegative")),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_job_runs_requested_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_runs")),
    )
    op.create_index(op.f("ix_job_runs_requested_by"), "job_runs", ["requested_by"])
    op.create_index(op.f("ix_job_runs_status"), "job_runs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_job_runs_status"), table_name="job_runs")
    op.drop_index(op.f("ix_job_runs_requested_by"), table_name="job_runs")
    op.drop_table("job_runs")
