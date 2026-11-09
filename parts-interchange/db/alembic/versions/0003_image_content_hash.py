"""image.imgcache_hash -> image.content_hash, indexed.

The column holds the BLAKE3 hash of the image bytes. Under the old name it read as "where the image is in
imgcache"; parts-direct now stores images in the part-images bucket (uploaded=true) and records the hash there
too, for dedupe. imgcache_bucket keeps its meaning: set only while the bytes live in imgcache.

Also drops idx_image_imgcache_hash, created by the pre-Alembic script
parts-direct/singlethreaded-scraper/src/migrations/002_image_imgcache_columns.sql where it was run.

Revision ID: 0003_image_content_hash
Revises: 0002_scrape_keys
Create Date: 2026-10-17

"""
from alembic import op


revision = '0003_image_content_hash'
down_revision = '0002_scrape_keys'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_image_imgcache_hash")
    op.alter_column('image', 'imgcache_hash', new_column_name='content_hash')
    op.create_index(op.f('ix_image_content_hash'), 'image', ['content_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_image_content_hash'), table_name='image')
    op.alter_column('image', 'content_hash', new_column_name='imgcache_hash')
