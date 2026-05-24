"""Initial junkyard_inventory schema

Revision ID: 0001
Revises:
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_location_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("chain", sa.String(100), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(10), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_location_id", name="uq_location_source"),
    )
    op.create_index("ix_locations_source", "locations", ["source"])

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("vin", sa.String(17), nullable=True),
        sa.Column("row", sa.String(20), nullable=True),
        sa.Column("arrival_date", sa.DateTime(), nullable=True),
        sa.Column("color", sa.String(100), nullable=True),
        sa.Column("trim", sa.String(200), nullable=True),
        sa.Column("vehicle_type", sa.String(100), nullable=True),
        sa.Column("body_type", sa.String(100), nullable=True),
        sa.Column("body_sub_type", sa.String(100), nullable=True),
        sa.Column("doors", sa.Integer(), nullable=True),
        sa.Column("style", sa.String(200), nullable=True),
        sa.Column("drive_type", sa.String(50), nullable=True),
        sa.Column("fuel_type", sa.String(50), nullable=True),
        sa.Column("engine_block", sa.String(10), nullable=True),
        sa.Column("engine_cylinders", sa.Integer(), nullable=True),
        sa.Column("engine_size", sa.Float(), nullable=True),
        sa.Column("engine_aspiration", sa.String(50), nullable=True),
        sa.Column("trans_type", sa.String(10), nullable=True),
        sa.Column("trans_speeds", sa.Integer(), nullable=True),
        sa.Column("mileage", sa.Integer(), nullable=True),
        sa.Column("preview_image_url", sa.String(500), nullable=True),
        sa.Column("detail_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("extras", JSONB(), nullable=True),
        sa.Column("car_id", sa.Integer(), nullable=True),
        sa.Column("car_id_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("car_id_method", sa.String(20), nullable=True),
        sa.Column("car_id_confidence", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_key", name="uq_vehicle_source"),
    )
    op.create_index("ix_vehicles_location_id", "vehicles", ["location_id"])
    op.create_index("ix_vehicles_source", "vehicles", ["source"])
    op.create_index("ix_vehicles_vin", "vehicles", ["vin"])
    op.create_index("ix_vehicles_car_id", "vehicles", ["car_id"])

    op.create_table(
        "mapping_rules",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("raw_value", sa.String(200), nullable=False),
        sa.Column("canonical_value", sa.String(200), nullable=False),
        sa.Column("make_context", sa.String(100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column("llm_rationale", sa.String(1000), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("total_in_feed", sa.Integer(), nullable=True),
        sa.Column("new_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])

    op.create_table(
        "mapping_discrepancies",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("raw_year", sa.String(20), nullable=True),
        sa.Column("raw_make", sa.String(100), nullable=True),
        sa.Column("raw_model", sa.String(200), nullable=True),
        sa.Column("raw_trim", sa.String(200), nullable=True),
        sa.Column("fuzzy_make_match", sa.String(100), nullable=True),
        sa.Column("fuzzy_make_score", sa.Float(), nullable=True),
        sa.Column("fuzzy_model_match", sa.String(200), nullable=True),
        sa.Column("fuzzy_model_score", sa.Float(), nullable=True),
        sa.Column("candidate_car_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="unresolved"),
        sa.Column("resolved_car_id", sa.Integer(), nullable=True),
        sa.Column("resolved_by_rule_id", sa.Integer(), sa.ForeignKey("mapping_rules.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_discrepancy_vehicle"),
    )


def downgrade() -> None:
    op.drop_table("mapping_discrepancies")
    op.drop_index("ix_scrape_runs_source", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_table("mapping_rules")
    op.drop_index("ix_vehicles_car_id", table_name="vehicles")
    op.drop_index("ix_vehicles_vin", table_name="vehicles")
    op.drop_index("ix_vehicles_source", table_name="vehicles")
    op.drop_index("ix_vehicles_location_id", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index("ix_locations_source", table_name="locations")
    op.drop_table("locations")
