"""Upsert keys and scrape_target for update scraper v2.

See parts-interchange/parts-direct/update-scraper/docs/design-v2.md §3.1. The unique keys were checked
duplicate-free on prod on 2026-10-11 before this was written.

Revision ID: 0002_scrape_keys
Revises: 0001_baseline
Create Date: 2026-10-11 01:42:45.086058

"""
from alembic import op
import sqlalchemy as sa


revision = '0002_scrape_keys'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('scrape_target',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('manufacturer_id', sa.Integer(), nullable=False),
    sa.Column('year', sa.String(length=120), nullable=False),
    sa.Column('make', sa.String(length=120), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('trim', sa.String(length=120), nullable=True),
    sa.Column('engine', sa.String(length=120), nullable=True),
    sa.Column('page_url', sa.String(length=1000), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('car_id', sa.Integer(), nullable=True),
    sa.Column('last_scraped_at', sa.DateTime(), nullable=True),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.String(length=1000), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['car_id'], ['car.id'], ),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturer.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('manufacturer_id', 'year', 'make', 'model', 'trim', 'engine', name='uq_scrape_target_vehicle', postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_scrape_target_car_id'), 'scrape_target', ['car_id'], unique=False)
    op.create_index('ix_scrape_target_queue', 'scrape_target', ['manufacturer_id', 'status', 'last_scraped_at'], unique=False)
    op.create_unique_constraint('uq_car_vehicle', 'car', ['manufacturer_id', 'year_id', 'make_id', 'model_id', 'trim_id', 'engine_id'], postgresql_nulls_not_distinct=True)
    op.create_unique_constraint('uq_image_manufacturer_name', 'image', ['manufacturer_id', 'name'])
    op.create_unique_constraint('uq_model_make_select', 'model', ['make_id', 'select_value'])
    op.create_unique_constraint('uq_part_manufacturer_number', 'part', ['manufacturer_id', 'part_number'])
    op.create_unique_constraint('uq_subcategory_category_name', 'subcategory', ['category_id', 'name'])


def downgrade() -> None:
    op.drop_constraint('uq_subcategory_category_name', 'subcategory', type_='unique')
    op.drop_constraint('uq_part_manufacturer_number', 'part', type_='unique')
    op.drop_constraint('uq_model_make_select', 'model', type_='unique')
    op.drop_constraint('uq_image_manufacturer_name', 'image', type_='unique')
    op.drop_constraint('uq_car_vehicle', 'car', type_='unique')
    op.drop_index('ix_scrape_target_queue', table_name='scrape_target')
    op.drop_index(op.f('ix_scrape_target_car_id'), table_name='scrape_target')
    op.drop_table('scrape_target')
