"""Discrepancy reasons + NHTSA decode on mapping_discrepancies; decode_mappings table

Admin rewrite phase 1 (junkyard-platform/docs/admin-rewrite-design.md §2.1-2.2). Additive only:
existing rows keep reason/nhtsa_* null until the worker re-resolves them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mapping_discrepancies", sa.Column("reason", sa.String(40), nullable=True))
    op.add_column("mapping_discrepancies", sa.Column("nhtsa_year", sa.String(10), nullable=True))
    op.add_column("mapping_discrepancies", sa.Column("nhtsa_make", sa.String(100), nullable=True))
    op.add_column("mapping_discrepancies", sa.Column("nhtsa_model", sa.String(200), nullable=True))
    op.add_column("mapping_discrepancies", sa.Column("nhtsa_series", sa.String(200), nullable=True))
    # The discrepancies page groups by these.
    op.create_index("ix_discrepancies_reason_decode", "mapping_discrepancies",
                    ["status", "reason", "nhtsa_make", "nhtsa_model"])

    op.create_table(
        "decode_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nhtsa_make", sa.String(100), nullable=False),
        sa.Column("nhtsa_model", sa.String(200), nullable=False),
        sa.Column("nhtsa_series", sa.String(200), nullable=True),
        sa.Column("make_key", sa.String(100), nullable=False),
        sa.Column("model_key", sa.String(200), nullable=False),
        sa.Column("series_key", sa.String(200), nullable=True),
        sa.Column("year_from", sa.Integer(), nullable=True),
        sa.Column("year_to", sa.Integer(), nullable=True),
        sa.Column("catalogue_make", sa.String(120), nullable=False),
        sa.Column("catalogue_model", sa.String(120), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_decode_mappings_key", "decode_mappings", ["make_key", "model_key"])


def downgrade() -> None:
    op.drop_index("ix_decode_mappings_key", table_name="decode_mappings")
    op.drop_table("decode_mappings")
    op.drop_index("ix_discrepancies_reason_decode", table_name="mapping_discrepancies")
    for col in ("nhtsa_series", "nhtsa_model", "nhtsa_make", "nhtsa_year", "reason"):
        op.drop_column("mapping_discrepancies", col)
