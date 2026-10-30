"""Fix suggestions

matching-v2 phase 3 (junkyard-platform/docs/matching-v2-design.md §3.2-3.3). Additive only: a new table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fix_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("group_key", JSONB(), nullable=False),
        sa.Column("group_ref", sa.String(64), nullable=False),
        sa.Column("proposal_ref", sa.String(64), nullable=False),
        sa.Column("proposal", JSONB(), nullable=False),
        sa.Column("preview", JSONB(), nullable=False),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt", sa.String(50), nullable=True),
        sa.Column("filed_by", sa.String(100), nullable=False),
        sa.Column("filed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(500), nullable=True),
        sa.Column("final", JSONB(), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
    )
    op.create_index("ix_fix_suggestions_group", "fix_suggestions", ["group_ref", "status"])


def downgrade() -> None:
    op.drop_index("ix_fix_suggestions_group", table_name="fix_suggestions")
    op.drop_table("fix_suggestions")
