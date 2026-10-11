"""Baseline: parts_interchange as deployed on 2026-10-11 (created by create_all / parts-loader-v2).

Empty on purpose: existing databases are stamped at this revision (`alembic stamp 0001_baseline`).
A brand-new database is built with create_all() and then stamped at head; replaying revisions from
an empty schema is not supported, since this baseline creates nothing.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
