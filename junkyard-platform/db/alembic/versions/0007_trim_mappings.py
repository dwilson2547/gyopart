"""How a VIN match was narrowed, and trim mappings

matching-v2 phase 2 (junkyard-platform/docs/matching-v2-design.md §2.2-2.3). Additive only: existing vehicles keep
the new columns null until the worker re-matches them (requeue vin_candidates after deploying).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("car_id_match_steps", ARRAY(sa.String(20)), nullable=True))
    op.add_column("vehicles", sa.Column("car_id_trim_unread", sa.String(200), nullable=True))
    # The Trims tab groups ambiguous vehicles by the trim text the matcher couldn't read.
    op.create_index("ix_vehicles_trim_unread", "vehicles", ["car_id_trim_unread"],
                    postgresql_where=sa.text("car_id_trim_unread IS NOT NULL"))

    op.create_table(
        "trim_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nhtsa_make", sa.String(100), nullable=False),
        sa.Column("nhtsa_model", sa.String(200), nullable=True),
        sa.Column("trim_text", sa.String(200), nullable=False),
        sa.Column("make_key", sa.String(100), nullable=False),
        sa.Column("model_key", sa.String(200), nullable=True),
        sa.Column("trim_key", sa.String(200), nullable=False),
        sa.Column("year_from", sa.Integer(), nullable=True),
        sa.Column("year_to", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("catalogue_trims", ARRAY(sa.String(120)), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_trim_mappings_key", "trim_mappings", ["make_key", "trim_key"])


def downgrade() -> None:
    op.drop_index("ix_trim_mappings_key", table_name="trim_mappings")
    op.drop_table("trim_mappings")
    op.drop_index("ix_vehicles_trim_unread", table_name="vehicles")
    op.drop_column("vehicles", "car_id_trim_unread")
    op.drop_column("vehicles", "car_id_match_steps")
