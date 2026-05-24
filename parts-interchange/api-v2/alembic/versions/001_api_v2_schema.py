"""api_v2_schema

Revision ID: 001
Revises:
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Convert positions TEXT → TEXT[] splitting on commas
    op.execute("""
        ALTER TABLE part
        ALTER COLUMN positions TYPE TEXT[]
        USING CASE
            WHEN positions IS NULL OR positions = '' THEN NULL
            ELSE string_to_array(regexp_replace(positions, '\\s*,\\s*', ',', 'g'), ',')
        END
    """)

    # Drop columns that were never populated
    op.drop_column('part', 'replaces')
    op.drop_column('part', 'notes')

    # Junkyard tables
    op.create_table(
        'junkyard',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('address', sa.Text),
        sa.Column('city', sa.Text),
        sa.Column('state', sa.Text),
        sa.Column('zip', sa.Text),
        sa.Column('lat', sa.Float),
        sa.Column('lng', sa.Float),
        sa.Column('phone', sa.Text),
        sa.Column('website', sa.Text),
        sa.Column('active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'scrape_site_config',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('junkyard_id', sa.Integer, sa.ForeignKey('junkyard.id')),
        sa.Column('site_type', sa.Text, nullable=False),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('scrape_interval_hours', sa.Integer, server_default='24'),
        sa.Column('enabled', sa.Boolean, server_default='true'),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'scrape_job',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('scrape_site_config_id', sa.Integer, sa.ForeignKey('scrape_site_config.id')),
        sa.Column('status', sa.Text, nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('error_message', sa.Text),
    )

    op.create_table(
        'junkyard_inventory',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('junkyard_id', sa.Integer, sa.ForeignKey('junkyard.id'), nullable=False),
        sa.Column('scrape_job_id', sa.Integer, sa.ForeignKey('scrape_job.id')),
        sa.Column('year', sa.Text, nullable=False),
        sa.Column('make_name', sa.Text, nullable=False),
        sa.Column('model_name', sa.Text, nullable=False),
        sa.Column('trim_name', sa.Text),
        sa.Column('date_listed', sa.Date),
        sa.Column('date_removed', sa.Date),
        sa.Column('price', sa.Numeric(10, 2)),
        sa.Column('row_location', sa.Text),
        sa.Column('vin', sa.Text),
        sa.Column('raw_data', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_junkyard_inventory_lookup',
                    'junkyard_inventory',
                    ['junkyard_id', 'year',
                     sa.text('lower(make_name)'), sa.text('lower(model_name)')])
    op.create_index('ix_junkyard_inventory_vin',
                    'junkyard_inventory', ['vin'],
                    postgresql_where=sa.text('vin IS NOT NULL'))


def downgrade():
    op.drop_table('junkyard_inventory')
    op.drop_table('scrape_job')
    op.drop_table('scrape_site_config')
    op.drop_table('junkyard')
    op.add_column('part', sa.Column('replaces', sa.Text))
    op.add_column('part', sa.Column('notes', sa.Text))
    op.execute("ALTER TABLE part ALTER COLUMN positions TYPE TEXT USING array_to_string(positions, ',')")
