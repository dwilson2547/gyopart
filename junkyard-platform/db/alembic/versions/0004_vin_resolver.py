"""Live VIN resolver: full NHTSA record in vin_cache, candidate cars + queue marker on vehicles

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vin_cache", sa.Column("raw", postgresql.JSONB(), nullable=True))
    op.add_column("vehicles", sa.Column("car_id_candidates", postgresql.ARRAY(sa.Integer()), nullable=True))
    op.add_column("vehicles", sa.Column("resolve_attempted_at", sa.DateTime(), nullable=True))
    # The resolver's queue: unresolved vehicles it has not processed yet.
    op.create_index(
        "ix_vehicles_resolve_queue", "vehicles", ["id"],
        postgresql_where=sa.text("car_id_resolved = false AND resolve_attempted_at IS NULL"),
    )
    # Part lookups match yard vehicles by overlap with a part's car ids.
    op.create_index("ix_vehicles_car_id_candidates", "vehicles", ["car_id_candidates"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_vehicles_car_id_candidates", table_name="vehicles")
    op.drop_index("ix_vehicles_resolve_queue", table_name="vehicles")
    op.drop_column("vehicles", "resolve_attempted_at")
    op.drop_column("vehicles", "car_id_candidates")
    op.drop_column("vin_cache", "raw")
