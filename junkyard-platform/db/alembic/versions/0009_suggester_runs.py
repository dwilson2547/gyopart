"""Suggester runs and attempts

matching-v2 phase 5 (junkyard-platform/docs/matching-v2-design.md §3.4). Additive only: two new tables.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suggester_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("counts", JSONB(), nullable=True),
        sa.Column("error", sa.String(1000), nullable=True),
    )
    op.create_table(
        "suggester_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("suggester_runs.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("group_key", JSONB(), nullable=False),
        sa.Column("group_ref", sa.String(64), nullable=False),
        sa.Column("vehicles", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("reply", JSONB(), nullable=True),
        sa.Column("suggestion_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_suggester_attempts_group", "suggester_attempts", ["group_ref", "id"])


def downgrade() -> None:
    op.drop_index("ix_suggester_attempts_group", table_name="suggester_attempts")
    op.drop_table("suggester_attempts")
    op.drop_table("suggester_runs")
