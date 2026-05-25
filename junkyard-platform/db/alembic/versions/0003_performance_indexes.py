"""Add performance indexes for inventory search and admin UI

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_vehicles_active_resolved
        ON vehicles(car_id)
        WHERE is_active = true AND car_id_resolved = true
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mapping_rules_active_field
        ON mapping_rules(is_active, field)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mapping_discrepancies_status
        ON mapping_discrepancies(status)
    """)


def downgrade() -> None:
    op.drop_index("ix_mapping_discrepancies_status", table_name="mapping_discrepancies", if_exists=True)
    op.drop_index("ix_mapping_rules_active_field",   table_name="mapping_rules",         if_exists=True)
    op.drop_index("ix_vehicles_active_resolved",     table_name="vehicles",              if_exists=True)
