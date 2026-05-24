"""Add vin_cache table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vin_cache",
        sa.Column("vin",        sa.String(17),  nullable=False),
        sa.Column("make",       sa.String(100), nullable=True),
        sa.Column("model",      sa.String(200), nullable=True),
        sa.Column("model_year", sa.String(10),  nullable=True),
        sa.Column("trim",       sa.String(200), nullable=True),
        sa.Column("error_code", sa.String(20),  nullable=True),
        sa.Column("fetched_at", sa.DateTime(),  nullable=False),
        sa.PrimaryKeyConstraint("vin"),
    )
    op.create_index("ix_vin_cache_fetched_at", "vin_cache", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_vin_cache_fetched_at", table_name="vin_cache", if_exists=True)
    op.drop_table("vin_cache")
