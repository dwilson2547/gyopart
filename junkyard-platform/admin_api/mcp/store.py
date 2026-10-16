"""The MCP OAuth tables (migration 0006). Admin-only, so they live here rather than in junkyard_common.

There is no user table: the admin's users are whoever authentik lets in, and the signed-in session carries
{sub, name, email}. Codes and grants keep that dict, so writes made through a grant can be attributed.
"""
from __future__ import annotations

import datetime
import secrets

from sqlalchemy import JSON, Column, DateTime, ForeignKey, MetaData, String, Table

metadata = MetaData()


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def new_id() -> str:
    return secrets.token_hex(16)


clients = Table(
    "mcp_oauth_clients", metadata,
    # The SDK's OAuthClientInformationFull as JSON, secret included: the SDK compares it in plain text, and PKCE
    # is what actually protects the code exchange.
    Column("client_id", String(64), primary_key=True),
    Column("info", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
)

requests = Table(
    "mcp_oauth_requests", metadata,
    # An /authorize request waiting on the consent page. user_sub and nonce are filled when the page is shown, so
    # only that signed-in user's form submission can approve it.
    Column("id", String(64), primary_key=True),
    Column("client_id", String(64), ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False),
    Column("params", JSON, nullable=False),
    Column("user_sub", String(200)),
    Column("nonce", String(64)),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

codes = Table(
    "mcp_oauth_codes", metadata,
    Column("code_hash", String(64), primary_key=True),
    Column("client_id", String(64), ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False),
    Column("user", JSON, nullable=False),
    Column("params", JSON, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

grants = Table(
    "mcp_oauth_grants", metadata,
    # One connected app for one user: the current access and refresh token, rotated in place on refresh. Deleting
    # the row disconnects the app.
    Column("id", String(32), primary_key=True, default=new_id),
    Column("user_sub", String(200), nullable=False, index=True),
    Column("user", JSON, nullable=False),
    Column("client_id", String(64), ForeignKey("mcp_oauth_clients.client_id", ondelete="CASCADE"), nullable=False,
           index=True),
    Column("client_name", String(100), nullable=False),
    Column("scopes", String(200), nullable=False, default=""),
    Column("resource", String(300)),
    Column("access_hash", String(64), nullable=False, unique=True),
    Column("access_expires_at", DateTime(timezone=True), nullable=False),
    Column("refresh_hash", String(64), nullable=False, unique=True),
    Column("refresh_expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utcnow),
    Column("last_used_at", DateTime(timezone=True)),
)
