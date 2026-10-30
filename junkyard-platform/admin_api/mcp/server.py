"""The discrepancy-fix MCP server (docs/admin-rewrite-design.md §2.7): what an agent sees.

Streamable HTTP at /mcp, stateless, JSON responses. Every request carries a bearer token issued through OAuth
(oauth.py); McpAuth rejects anything else before the SDK sees it. The tools call the same functions as the JSON
API, so a fix made here is checked, written and requeued exactly as one made in the UI.
"""
from __future__ import annotations

from typing import Annotated, Any, Callable, Literal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings

from junkyard_common.models import Location, MappingDiscrepancy, Vehicle, VinCache
from pipeline.pi_schema import (pi_car_table, pi_engine_table, pi_make_table, pi_model_table, pi_trim_table,
                                pi_year_table)

from ..api import catalogue, discrepancies, fixes, suggestions, trims, vehicles
from ..api.common import BUCKETS, IGNORED, engines, open_discrepancies, sql_year
from ..api.discrepancies import GroupKey, key_filter
from . import oauth

INSTRUCTIONS = """\
You are fixing vehicle-matching discrepancies in a junkyard inventory, acting for the signed-in user.

How matching works: every yard vehicle's VIN is decoded by NHTSA (cached), and the decode's year, make,
model and series are matched to the parts catalogue (year, make, model, trim, engine). A vehicle that
doesn't match gets a discrepancy with a reason:
- model_not_in_catalogue / make_not_in_catalogue (tab "fixable"): NHTSA's name differs from the
  catalogue's (e.g. "C-Class" vs "C 230"/"C 300", "Geo Prizm" vs Chevrolet "Prizm"). Fix with a
  decode mapping from the NHTSA make/model (optionally series and years) to catalogue models.
  Cross-make targets are allowed.
- year_not_in_catalogue / model_year_gap (tab "gaps"): the names match but the catalogue lacks those
  years. Usually not a naming problem; only map when the decode names a different catalogue model
  that does cover those years. Never map to a model just because it exists in other years.
- no_vin / decode_failed (tab "nodecode"): no usable decode, grouped by yard and the yard's own
  make/model strings. Fix with a yard rule (yard string -> catalogue make/model).
- trim_unread (tab "trims"): not a discrepancy. These vehicles matched, but to several catalogue cars that
  differ by trim, and their trim text (NHTSA Trim/Series, or the yard's) couldn't be read: maker-internal
  grades ("Middle level", Kia "GL"), body words ("Styleside"). Grouped by decode make, model and that text.
  Fix with a trim mapping: action "map" to the catalogue trim(s) it means (from the group's candidateTrims),
  or "noise" when it says nothing about the trim. Map only when the text clearly names that trim; a wrong
  map turns "one of these" into a confident wrong match. Several trims is fine when it could be any of them.

Workflow:
1. discrepancy_overview, then list_discrepancy_groups (most open vehicles first = highest priority).
2. get_discrepancy_group for one group: catalogue coverage by year, suggested catalogue models,
   existing mappings, sample vehicles. Pull more examples with list_group_vehicles
   (include_decode=true for the NHTSA fields: trim, engine, body class, etc.) or get_vehicle.
3. Check targets with catalogue_models / catalogue_cars. Targets must exist in the catalogue.
4. preview_mapping / preview_yard_rule: runs the real matcher over the affected vehicles. Only create
   when the preview matches what you expect (wouldMatch, exact, and what stays unmatched).
5. create_mapping / create_yard_rule writes it and requeues the vehicles; the worker re-matches them
   within seconds. Re-read the group to confirm.
- Prefer one mapping per decode with several targets (e.g. C-Class -> C 230, C 240, C 320) over
  guessing one; the matcher picks among targets by year, trim and engine.
- Narrow by series or years when only part of a decode maps to a model.
- set_group_ignored hides a group that can never match (not a car in the catalogue's sense); say why.
- Trim groups: preview_trim_mapping reports how many covered vehicles end exact / narrower / unchanged /
  wider; "wider" or a drop in exact means the mapping overrides a reading that worked: narrow it.
- delete_mapping / delete_trim_mapping only work on mappings agents made. Mappings the user made are theirs to
  change.
- When unsure, stop and ask the user rather than creating a doubtful mapping.

Suggesting instead of fixing: when the user asks for suggestions (or isn't there to confirm), use suggest_fix.
It files the fix, with its preview and your rationale, for the user to approve, tweak or reject on the admin
UI's Suggestions page, and changes nothing until they do. You can't approve suggestions. One suggestion waits
per group at a time; a fix the user rejected for a group is never filed again. list_suggestions shows what is
waiting and how earlier ones were reviewed (rejection reasons say what the user disagreed with).
"""

SCHEME = "Bearer"
RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
D, V = MappingDiscrepancy, Vehicle
Tab = Literal["fixable", "gaps", "nodecode", "trims", "ignored"]
Targets = Annotated[list[fixes.Target], Field(min_length=1, description=(
    "Catalogue make + model pairs; several when the decode can be any of them"))]
TrimMake = Annotated[str, Field(description="NHTSA make, as in the trim group key")]
TrimText = Annotated[str, Field(description="The trim text, as in the trim group key")]
# NHTSA's placeholders for "no value"; dropped from decodes so a record is ~20 fields, not ~140.
_EMPTY = {"", "Not Applicable", "null", "None"}


def compact_decode(raw: dict | None) -> dict:
    return {k: v for k, v in (raw or {}).items() if v is not None and str(v).strip() not in _EMPTY}


class McpAuth:
    """Bearer-token gate in front of the SDK's ASGI app. A 401 points the client at the protected-resource
    metadata (RFC 9728), which is how an OAuth-capable client discovers it can sign the user in."""

    def __init__(self, inner: ASGIApp, engine: Callable, public_url: str):
        self.inner, self.engine, self.public_url = inner, engine, public_url.rstrip("/")
        self.metadata_url = self.public_url + RESOURCE_METADATA_PATH

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raw = oauth.bearer(dict(scope["headers"]).get(b"authorization", b"").decode("latin-1"))
            ok = False
            if raw:
                with self.engine().begin() as conn:
                    ok = oauth.principal(conn, raw) is not None
            if not ok:
                challenge = f'{SCHEME} error="invalid_token", resource_metadata="{self.metadata_url}"'
                res = JSONResponse({"error": "invalid_token",
                                    "error_description": "sign in through your MCP client"},
                                   status_code=401, headers={"WWW-Authenticate": challenge})
                await res(scope, receive, send)
                return
        await self.inner(scope, receive, send)


def _ji():
    return engines()[0]


def build(public_url: str) -> tuple[MCPServer, ASGIApp]:
    server = MCPServer(name="junkyard-admin", instructions=INSTRUCTIONS, website_url=public_url)

    def run(ctx: Context, fn: Callable[..., Any], write: bool = False) -> Any:
        raw = oauth.bearer((ctx.headers or {}).get("authorization"))
        try:
            eng = engines()
            with eng[0].begin() as conn:
                who = oauth.principal(conn, raw)
            if who is None:
                raise ToolError("not signed in: the token is missing, expired or revoked")
            return fn(eng, who) if write else fn(eng)
        except HTTPException as exc:
            d = exc.detail
            raise ToolError(d.get("message", str(d)) if isinstance(d, dict) else str(d)) from None

    # ── reading discrepancies ─────────────────────────────────────────────────────────────────────────────

    @server.tool()
    def discrepancy_overview(ctx: Context, yard: Annotated[str | None, Field(
            description="Limit to one yard (a source name from the yards list)")] = None) -> dict:
        """Open discrepancies at a glance: groups and vehicles per tab, vehicles per reason, and per yard
        (active vehicles, unmatched). Start here."""
        def go(eng):
            with Session(eng[0]) as s:
                q = open_discrepancies(select(D.reason, func.count()).select_from(D).join(V, V.id == D.vehicle_id))
                if yard:
                    q = q.where(V.source == yard)
                reasons = dict(s.execute(q.group_by(D.reason)).all())
                return {"tabs": discrepancies.summary(s, yard=yard),
                        "tabReasons": {t: list(r) for t, r in BUCKETS.items()},
                        "byReason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
                        "yards": discrepancies.get_yards(eng)}
        return run(ctx, go)

    @server.tool()
    def list_discrepancy_groups(
            ctx: Context, tab: Tab = "fixable",
            yard: str | None = None,
            make: Annotated[str | None, Field(description="NHTSA make (or the yard's make, on nodecode)")] = None,
            search: Annotated[str | None, Field(description="Text in the make, model or series")] = None,
            page: Annotated[int, Field(ge=1)] = 1) -> dict:
        """Discrepancy groups, most open vehicles first (that order is the priority). A group is one NHTSA
        decode (make, model, series) or, on nodecode, one yard + the yard's own make/model. Pass a group's
        `key` unchanged to the other tools. 50 per page."""
        return run(ctx, lambda eng: _with_session(eng, lambda s: discrepancies.groups(
            s, tab, yard=yard, make=make, search=search, page=page)))

    @server.tool()
    def get_discrepancy_group(ctx: Context, key: GroupKey,
                              status: Literal["open", "ignored"] = "open",
                              samples: Annotated[int, Field(ge=0, le=30)] = 10) -> dict:
        """One group: vehicles by reason, yard and year; for decode groups the catalogue make, the years the
        catalogue has for the make and for this model (modelYears), ranked catalogue model suggestions with
        their years, and existing mappings; for yard groups make and model suggestions; for trim groups the
        catalogue trims among the vehicles' candidates (candidateTrims: how many vehicles could be each, with
        models and years) and existing trim mappings for the text. Plus recent sample vehicles."""
        def go(eng):
            with Session(eng[0]) as s:
                out = discrepancies.detail(s, eng[1], key, status)
            out["samples"] = out["samples"][:samples]
            return out
        return run(ctx, go)

    @server.tool()
    def list_group_vehicles(
            ctx: Context, key: GroupKey,
            year: Annotated[int | None, Field(description="Decode year (decode groups) or yard year")] = None,
            yard: str | None = None,
            include_decode: Annotated[bool, Field(description="Add each vehicle's NHTSA decode")] = False,
            status: Literal["open", "ignored"] = "open",
            limit: Annotated[int, Field(ge=1, le=100)] = 20,
            offset: Annotated[int, Field(ge=0)] = 0) -> dict:
        """Specific vehicles in a group, newest arrivals first, optionally with their NHTSA decodes (empty
        fields dropped). Use it to see what trims, engines or body styles a group really contains."""
        def go(eng):
            with Session(eng[0]) as s:
                if key.kind == "trim":
                    q = (trims._unread().add_columns(V.id, V.vin, V.source, V.source_key, V.year, V.make, V.model,
                                                     V.trim, Location.name, literal(trims.UNREAD), VinCache.raw)
                         .join(Location, Location.id == V.location_id)
                         .where(*trims._group_where(key.make, key.model, key.trim)))
                    if year is not None:
                        q = q.where(sql_year(VinCache.model_year) == year)
                else:
                    q = (select(V.id, V.vin, V.source, V.source_key, V.year, V.make, V.model, V.trim, Location.name,
                                D.reason, VinCache.raw)
                         .join(D, D.vehicle_id == V.id).join(Location, Location.id == V.location_id)
                         .outerjoin(VinCache, VinCache.vin == V.vin).where(key_filter(key)))
                    q = open_discrepancies(q, status)
                    if year is not None:
                        q = q.where((sql_year(D.nhtsa_year) if key.kind == "decode" else V.year) == year)
                if yard:
                    q = q.where(V.source == yard)
                total = s.execute(select(func.count()).select_from(q.subquery())).scalar()
                rows = s.execute(q.order_by(V.arrival_date.desc().nullslast(), V.id.desc())
                                 .offset(offset).limit(limit)).all()
            out = []
            for r in rows:
                v = {"id": r[0], "vin": r[1], "yard": r[2], "stock": r[3], "year": r[4], "make": r[5],
                     "model": r[6], "trim": r[7], "location": r[8], "reason": r[9]}
                if include_decode:
                    v["decode"] = compact_decode(r[10])
                out.append(v)
            return {"total": total, "offset": offset, "vehicles": out}
        return run(ctx, go)

    @server.tool()
    def get_vehicle(ctx: Context,
                    vehicle_id: int | None = None,
                    vin: str | None = None,
                    stock: Annotated[str | None, Field(description="The yard's stock number")] = None) -> dict:
        """One vehicle by id, VIN or stock number: the yard's fields, match state (method, candidates as
        catalogue cars), its discrepancy, and its NHTSA decode. A stock number shared by several yards
        returns the list to choose from."""
        def go(eng):
            vid = vehicle_id
            if vid is None:
                conds = []
                if vin:
                    conds.append(func.upper(V.vin) == vin.strip().upper())
                if stock:
                    conds.append(func.upper(V.source_key) == stock.strip().upper())
                if not conds:
                    raise ToolError("pass vehicle_id, vin or stock")
                with Session(eng[0]) as s:
                    hits = s.execute(select(V.id, V.source, V.is_active).where(or_(*conds))
                                     .order_by(V.is_active.desc(), V.last_seen_at.desc()).limit(10)).all()
                if not hits:
                    raise ToolError("no such vehicle")
                if len(hits) > 1 and len({h.source for h in hits}) > 1:
                    return {"matches": [{"id": h.id, "yard": h.source, "active": h.is_active} for h in hits]}
                vid = hits[0].id
            out = vehicles.vehicle(vid, eng=eng)
            if out.get("decode"):
                out["decode"]["raw"] = compact_decode(out["decode"]["raw"])
            return out
        return run(ctx, go)

    @server.tool()
    def get_vin_decode(ctx: Context, vin: str) -> dict:
        """The cached NHTSA decode for a VIN (empty fields dropped), and how many yard vehicles carry it."""
        def go(eng):
            with Session(eng[0]) as s:
                row = s.get(VinCache, vin.strip().upper())
                if row is None:
                    raise ToolError("no cached decode for that VIN")
                n = s.execute(select(func.count()).select_from(V).where(V.vin == row.vin)).scalar()
            return {"vin": row.vin, "year": row.model_year, "make": row.make, "model": row.model, "trim": row.trim,
                    "error": row.error_code, "fetchedAt": row.fetched_at.isoformat(), "vehicles": n,
                    "decode": compact_decode(row.raw)}
        return run(ctx, go)

    # ── the catalogue ─────────────────────────────────────────────────────────────────────────────────────

    @server.tool()
    def catalogue_makes(ctx: Context) -> list[dict]:
        """Every catalogue make with its first and last year."""
        return run(ctx, lambda eng: catalogue.makes(eng[1]))

    @server.tool()
    def catalogue_models(ctx: Context, make: str, year_from: int | None = None, year_to: int | None = None,
                         include_out_of_range: bool = False) -> list[dict]:
        """A make's catalogue models with the years each exists in; yearsInRange counts the years inside
        year_from..year_to. With a year range, only models present in it, unless include_out_of_range."""
        def go(eng):
            rows = catalogue.get_models(make, year_from, year_to, eng=eng)
            ranged = year_from is not None or year_to is not None
            return rows if include_out_of_range or not ranged else [m for m in rows if m["yearsInRange"]]
        return run(ctx, go)

    @server.tool()
    def suggest_catalogue_models(
            ctx: Context, make: Annotated[str, Field(description="Catalogue make to search")],
            names: Annotated[list[str], Field(description="Names to compare, e.g. the decode's model and "
                                                          "model + series")],
            year_from: int | None = None, year_to: int | None = None) -> list[dict]:
        """A make's catalogue models ranked for some names: models present in the years first, then by name
        similarity. Useful for cross-make targets (Geo Prizm -> Chevrolet)."""
        return run(ctx, lambda eng: catalogue.get_suggest(make, names, year_from, year_to, eng=eng))

    @server.tool()
    def catalogue_cars(
            ctx: Context, make: str,
            model: Annotated[str | None, Field(description="Exact catalogue model name")] = None,
            year: int | None = None, year_from: int | None = None, year_to: int | None = None,
            trim: Annotated[str | None, Field(description="Text in the trim name")] = None,
            engine: Annotated[str | None, Field(description="Text in the engine name, e.g. 3.2L or V6")] = None,
            limit: Annotated[int, Field(ge=1, le=200)] = 100) -> dict:
        """Catalogue car records (id, year, make, model, trim, engine): what a vehicle can be matched to."""
        def go(eng):
            c, y, mk, md, t, e = (pi_car_table.c, pi_year_table.c, pi_make_table.c, pi_model_table.c,
                                  pi_trim_table.c, pi_engine_table.c)
            yr = func.cast(y.name, c.id.type)
            q = (select(c.id, y.name, mk.name, md.name, t.name, e.name)
                 .join(pi_year_table, y.id == c.year_id).join(pi_make_table, mk.id == c.make_id)
                 .join(pi_model_table, md.id == c.model_id)
                 .outerjoin(pi_trim_table, t.id == c.trim_id).outerjoin(pi_engine_table, e.id == c.engine_id)
                 .where(func.lower(mk.name) == make.strip().lower()))
            if model:
                q = q.where(md.name == model)
            if year is not None:
                q = q.where(y.name == str(year))
            if year_from is not None:
                q = q.where(yr >= year_from)
            if year_to is not None:
                q = q.where(yr <= year_to)
            if trim:
                q = q.where(t.name.ilike(f"%{trim}%"))
            if engine:
                q = q.where(e.name.ilike(f"%{engine}%"))
            with eng[1].connect() as conn:
                total = conn.execute(select(func.count()).select_from(q.subquery())).scalar()
                rows = conn.execute(q.order_by(y.name, md.name, t.name, e.name).limit(limit)).all()
            return {"total": total, "cars": [{"id": r[0], "year": r[1], "make": r[2], "model": r[3], "trim": r[4],
                                              "engine": r[5]} for r in rows]}
        return run(ctx, go)

    # ── existing fixes ────────────────────────────────────────────────────────────────────────────────────

    @server.tool()
    def list_mappings(ctx: Context, nhtsa_make: str | None = None) -> list[dict]:
        """Decode mappings with who made them and how many active vehicles each covers (and how many of those
        are matched)."""
        def go(eng):
            rows = fixes.list_mappings(eng=eng)
            return [m for m in rows if not nhtsa_make or (m["nhtsaMake"] or "").lower() == nhtsa_make.lower()]
        return run(ctx, go)

    @server.tool()
    def list_trim_mappings(ctx: Context, nhtsa_make: str | None = None) -> list[dict]:
        """Trim mappings (NHTSA/yard trim text -> catalogue trims, or noise) with who made them and how many
        active VIN-matched vehicles each covers."""
        def go(eng):
            rows = trims.list_trim_mappings(eng)
            return [m for m in rows if not nhtsa_make or (m["nhtsaMake"] or "").lower() == nhtsa_make.lower()]
        return run(ctx, go)

    @server.tool()
    def list_yard_rules(ctx: Context) -> list[dict]:
        """Active yard rules (yard make/model string -> catalogue make/model)."""
        return run(ctx, lambda eng: fixes.list_rules(eng=eng))

    # ── fixes ─────────────────────────────────────────────────────────────────────────────────────────────

    def mapping_request(make, model, series, year_from, year_to, targets) -> fixes.MappingRequest:
        try:
            return fixes.MappingRequest(make=make, model=model, series=series, year_from=year_from,
                                        year_to=year_to, targets=targets)
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    @server.tool()
    def preview_mapping(
            ctx: Context,
            make: Annotated[str, Field(description="NHTSA make, as in the group key")],
            model: Annotated[str, Field(description="NHTSA model, as in the group key")],
            targets: Targets,
            series: Annotated[str | None, Field(description="Only this NHTSA series; omit for any")] = None,
            year_from: int | None = None, year_to: int | None = None) -> dict:
        """What a decode mapping would do, without writing anything: of the open vehicles it covers, how many
        would match (and how many to exactly one car), and why the rest still wouldn't."""
        req = mapping_request(make, model, series, year_from, year_to, targets)
        return run(ctx, lambda eng: fixes.preview_mapping(req, eng=eng))

    @server.tool()
    def create_mapping(
            ctx: Context,
            make: Annotated[str, Field(description="NHTSA make, as in the group key")],
            model: Annotated[str, Field(description="NHTSA model, as in the group key")],
            targets: Targets,
            series: Annotated[str | None, Field(description="Only this NHTSA series; omit for any")] = None,
            year_from: int | None = None, year_to: int | None = None) -> dict:
        """Create a decode mapping (one row per target) and requeue the vehicles it covers; the worker
        re-matches them within seconds. Returns the new mapping ids (for delete_mapping) and the preview it was
        created under."""
        req = mapping_request(make, model, series, year_from, year_to, targets)

        def go(eng, who):
            preview = fixes.preview_mapping(req, eng=eng)
            return {**fixes.save_mapping(eng, req, who.created_by), "preview": preview}
        return run(ctx, go, write=True)

    @server.tool()
    def delete_mapping(ctx: Context, mapping_id: int) -> dict:
        """Delete a mapping an agent made, and requeue every vehicle it covered."""
        return run(ctx, lambda eng, who: fixes.remove_mapping(eng, mapping_id, created_by_prefix=oauth.AGENT_PREFIX),
                   write=True)

    def trim_request(make, model, trim, action, catalogue_trims, year_from, year_to) -> trims.TrimMappingRequest:
        try:
            return trims.TrimMappingRequest(make=make, model=model, trim=trim, action=action,
                                            trims=catalogue_trims or [], year_from=year_from, year_to=year_to)
        except ValueError as exc:
            raise ToolError(str(exc)) from None

    @server.tool()
    def preview_trim_mapping(
            ctx: Context,
            make: TrimMake, trim: TrimText,
            action: Annotated[Literal["map", "noise"], Field(description="map to catalogue trims, or noise")],
            model: Annotated[str | None, Field(description="NHTSA model from the group key; omit for every "
                                                           "model of the make")] = None,
            catalogue_trims: Annotated[list[str] | None, Field(description="For map: catalogue trim names, from "
                                                                           "the group's candidateTrims")] = None,
            year_from: int | None = None, year_to: int | None = None) -> dict:
        """What a trim mapping would do, without writing anything: of the VIN-matched vehicles whose trim text
        it covers, how many end exact (and were before), narrower, unchanged or wider."""
        req = trim_request(make, model, trim, action, catalogue_trims, year_from, year_to)
        return run(ctx, lambda eng: trims.preview_trim_mapping_for(eng, req))

    @server.tool()
    def create_trim_mapping(
            ctx: Context,
            make: TrimMake, trim: TrimText,
            action: Annotated[Literal["map", "noise"], Field(description="map to catalogue trims, or noise")],
            model: Annotated[str | None, Field(description="NHTSA model from the group key; omit for every "
                                                           "model of the make")] = None,
            catalogue_trims: Annotated[list[str] | None, Field(description="For map: catalogue trim names, from "
                                                                           "the group's candidateTrims")] = None,
            year_from: int | None = None, year_to: int | None = None) -> dict:
        """Create a trim mapping and requeue the vehicles it covers; the worker re-matches them within seconds.
        Returns the new id (for delete_trim_mapping) and the preview it was created under."""
        req = trim_request(make, model, trim, action, catalogue_trims, year_from, year_to)

        def go(eng, who):
            preview = trims.preview_trim_mapping_for(eng, req)
            return {**trims.save_trim_mapping(eng, req, who.created_by), "preview": preview}
        return run(ctx, go, write=True)

    @server.tool()
    def delete_trim_mapping(ctx: Context, mapping_id: int) -> dict:
        """Delete a trim mapping an agent made, and requeue every vehicle it covered."""
        return run(ctx, lambda eng, who: trims.remove_trim_mapping(eng, mapping_id,
                                                                   created_by_prefix=oauth.AGENT_PREFIX),
                   write=True)

    def rule_request(source, raw_make, raw_model, make, model) -> fixes.RuleRequest:
        return fixes.RuleRequest(source=source, raw_make=raw_make, raw_model=raw_model, make=make, model=model)

    @server.tool()
    def preview_yard_rule(
            ctx: Context,
            make: Annotated[str, Field(description="Catalogue make")],
            raw_make: Annotated[str | None, Field(description="The yard's make string (group key make)")] = None,
            raw_model: Annotated[str | None, Field(description="The yard's model string (group key model)")] = None,
            model: Annotated[str | None, Field(description="Catalogue model; omit to fix only the make")] = None,
            source: Annotated[str | None, Field(description="Only this yard (group key source); omit for every "
                                                            "yard")] = None) -> dict:
        """What a yard rule would do for a nodecode group, without writing anything."""
        req = rule_request(source, raw_make, raw_model, make, model)
        return run(ctx, lambda eng: fixes.preview_rule(req, eng=eng))

    @server.tool()
    def create_yard_rule(
            ctx: Context,
            make: Annotated[str, Field(description="Catalogue make")],
            raw_make: Annotated[str | None, Field(description="The yard's make string (group key make)")] = None,
            raw_model: Annotated[str | None, Field(description="The yard's model string (group key model)")] = None,
            model: Annotated[str | None, Field(description="Catalogue model; omit to fix only the make")] = None,
            source: Annotated[str | None, Field(description="Only this yard (group key source); omit for every "
                                                            "yard")] = None) -> dict:
        """Create a yard rule (the yard's make/model strings -> catalogue make/model) and requeue the group's
        vehicles. Returns the preview it was created under."""
        req = rule_request(source, raw_make, raw_model, make, model)

        def go(eng, who):
            preview = fixes.preview_rule(req, eng=eng)
            return {**fixes.save_rule(eng, req, who.created_by), "preview": preview}
        return run(ctx, go, write=True)

    @server.tool()
    def set_group_ignored(ctx: Context, key: GroupKey, ignore: bool = True) -> dict:
        """Ignore a group that can never match (it moves to the ignored tab and stays there across
        re-matches), or un-ignore it."""
        def go(eng, who):
            with Session(eng[0]) as s:
                n = discrepancies.set_status(s, key, ignore)
                s.commit()
            return {"updated": n, "status": IGNORED if ignore else "open"}
        return run(ctx, go, write=True)

    # ── suggestions (filed for review; only a person approves them, in the admin UI) ──────────────────────

    @server.tool()
    def list_suggestions(
            ctx: Context,
            view: Annotated[Literal["pending", "reviewed", "rejected", "stale"], Field(description=(
                "pending = waiting for review; reviewed = approved or edited; stale = the group emptied first"))]
            = "pending",
            kind: suggestions.Kind | None = None) -> dict:
        """Fix suggestions with their proposal, the preview they were filed under, rationale and review outcome
        (who, when, the reject reason, or what the user changed before approving), plus counts per view."""
        return run(ctx, lambda eng: suggestions.list_suggestions(eng, view, kind))

    @server.tool()
    def suggest_fix(
            ctx: Context, kind: suggestions.Kind, key: GroupKey,
            proposal: Annotated[dict, Field(description=(
                "Exactly the arguments the matching create tool takes, for this group. decode_mapping: make, "
                "model, series?, year_from?, year_to?, targets [{make, model}]. trim_mapping: make, model?, trim, "
                "action map|noise, trims [catalogue trim names], year_from?, year_to?. yard_rule: make, model?, "
                "raw_make, raw_model, source?. ignore_group: {}."))],
            rationale: Annotated[str, Field(min_length=1, max_length=2000, description=(
                "Why: the evidence from the group (decodes, catalogue years, candidates) the user will check"))]) -> dict:
        """File a fix for the user to review instead of making it. Checked like a create (targets must exist in
        the catalogue, the fix must be for this group's decode / trim text / yard strings) and previewed; refused
        when the preview shows it would match nothing, when the group already has a suggestion waiting, or when
        the user rejected this same fix for it before. Writes no mapping and requeues nothing."""
        return run(ctx, lambda eng, who: suggestions.file_suggestion(
            eng, kind, key, proposal, rationale, model=who.client_name, filed_by=who.created_by), write=True)

    host = public_url.split("://", 1)[-1].split("/", 1)[0]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host, "localhost", "localhost:*", "127.0.0.1:*", "testserver"],
        allowed_origins=[public_url.rstrip("/"), "http://localhost:*", "http://127.0.0.1:*"])
    server.streamable_http_app(streamable_http_path="/mcp", json_response=True, stateless_http=True,
                               transport_security=security)
    return server, McpAuth(StreamableHTTPASGIApp(server.session_manager), _ji, public_url)


def _with_session(eng, fn):
    with Session(eng[0]) as s:
        return fn(s)
