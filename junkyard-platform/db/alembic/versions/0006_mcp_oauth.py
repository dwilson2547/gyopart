"""OAuth storage for the admin's MCP endpoint: registered clients, pending authorizations, codes, grants

Admin rewrite phase 7 (junkyard-platform/docs/admin-rewrite-design.md §2.7). New tables only. The admin owns
them (admin_api/mcp/store.py); nothing else reads them.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("info", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcp_oauth_requests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("client_id", sa.String(64),
                  sa.ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("user_sub", sa.String(200), nullable=True),
        sa.Column("nonce", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcp_oauth_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column("client_id", sa.String(64),
                  sa.ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user", sa.JSON(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcp_oauth_grants",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_sub", sa.String(200), nullable=False, index=True),
        sa.Column("user", sa.JSON(), nullable=False),
        sa.Column("client_id", sa.String(64),
                  sa.ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_name", sa.String(100), nullable=False),
        sa.Column("scopes", sa.String(200), nullable=False),
        sa.Column("resource", sa.String(300), nullable=True),
        sa.Column("access_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for t in ("mcp_oauth_grants", "mcp_oauth_codes", "mcp_oauth_requests", "mcp_oauth_clients"):
        op.drop_table(t)
