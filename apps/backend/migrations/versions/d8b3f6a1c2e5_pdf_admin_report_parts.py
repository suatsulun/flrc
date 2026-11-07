"""report set parts

A report ZIP larger than the output budget is stored as numbered parts: each part is a
`job_runs` row under the request, so it keeps the 24-hour blob store, the download route and
its authorization (ADR-024, ADR-077). Deleting a request deletes its parts.

Revision ID: d8b3f6a1c2e5
Revises: c4e7a2d9f318
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8b3f6a1c2e5"
down_revision: str | Sequence[str] | None = "c4e7a2d9f318"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("parent_id", sa.BigInteger(), nullable=True))
    op.add_column("job_runs", sa.Column("part", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_job_runs_parent_id_job_runs"),
        "job_runs",
        "job_runs",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_job_runs_parent_id"), "job_runs", ["parent_id"])


def downgrade() -> None:
    # Parts are only half of a download without their siblings; they go with the column.
    op.execute("DELETE FROM job_runs WHERE parent_id IS NOT NULL")
    op.drop_index(op.f("ix_job_runs_parent_id"), table_name="job_runs")
    op.drop_constraint(op.f("fk_job_runs_parent_id_job_runs"), "job_runs", type_="foreignkey")
    op.drop_column("job_runs", "part")
    op.drop_column("job_runs", "parent_id")
