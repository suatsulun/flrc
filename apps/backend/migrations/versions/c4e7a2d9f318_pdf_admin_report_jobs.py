"""report set jobs

Report cards return as background jobs (ADR-077). The retired per-card kinds
(`progress_pdf`, `german_karne`, `french_karne`) become the single
`report_set` kind, so their history stays listed. A retired job still waiting
would never run — no worker task handles it any more — so it is marked failed
instead of spinning in the downloads list forever.

Revision ID: c4e7a2d9f318
Revises: c41d7e9a2b58
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4e7a2d9f318"
down_revision: str | Sequence[str] | None = "c41d7e9a2b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETIRED_KINDS = "('progress_pdf','german_karne','french_karne')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_job_runs_kind_valid"), "job_runs", type_="check")
    op.execute(
        f"""
        UPDATE job_runs
        SET status = 'failed',
            error_code = 'report_job_retired',
            error_detail = 'The job failed. See server logs with this job id.',
            finished_at = now() AT TIME ZONE 'UTC'
        WHERE kind IN {RETIRED_KINDS} AND status IN ('queued', 'running')
        """
    )
    op.execute(f"UPDATE job_runs SET kind = 'report_set' WHERE kind IN {RETIRED_KINDS}")
    op.create_check_constraint(
        op.f("ck_job_runs_kind_valid"),
        "job_runs",
        "kind IN ('report_set','year_export')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_job_runs_kind_valid"), "job_runs", type_="check")
    # The old schema had no set-wide kind; its generic report kind keeps the history rows.
    op.execute("UPDATE job_runs SET kind = 'progress_pdf' WHERE kind = 'report_set'")
    op.create_check_constraint(
        op.f("ck_job_runs_kind_valid"),
        "job_runs",
        "kind IN ('progress_pdf','german_karne','french_karne','year_export')",
    )
