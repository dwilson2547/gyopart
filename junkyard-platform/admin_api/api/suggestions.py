"""Fix suggestions (matching-v2-design §3.2-3.3): a proposed fix waits here until a person approves, tweaks or
rejects it in the admin UI. Filing one (the MCP's suggest_fix, later the suggester job) writes nothing else and
requeues nothing; approving runs the same save as a manual fix. Approval exists only on this web API, which sits
behind the admin sign-in; the MCP can read and file suggestions, never approve them.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from junkyard_common.models import FixSuggestion, MappingDiscrepancy, Vehicle
from pipeline.car_matcher import name_key

from . import discrepancies, fixes, trims
from ..auth.web import who
from .common import engines, open_discrepancies
from .discrepancies import GroupKey, key_filter

router = APIRouter(prefix="/api", tags=["suggestions"])

Kind = Literal["decode_mapping", "trim_mapping", "yard_rule", "ignore_group"]
PENDING, APPROVED, EDITED, REJECTED, STALE = "pending", "approved", "edited", "rejected", "stale"


class IgnoreRequest(BaseModel):
    """Ignore the group: nothing to choose beyond the group itself."""


# What each kind's proposal is: exactly the request its create takes.
REQUESTS: dict[str, type[BaseModel]] = {"decode_mapping": fixes.MappingRequest,
                                        "trim_mapping": trims.TrimMappingRequest,
                                        "yard_rule": fixes.RuleRequest, "ignore_group": IgnoreRequest}
# Which group kinds each fix can be for.
FITS = {"decode_mapping": {"decode"}, "trim_mapping": {"trim"}, "yard_rule": {"yard"},
        "ignore_group": {"decode", "yard"}}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _invalid(field: str, message: str, status: int = 422):
    raise HTTPException(status, {"field": field, "message": message})


def _hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def group_ref(key: GroupKey) -> str:
    return _hash(key.model_dump())


def parse(kind: str, proposal: dict) -> BaseModel:
    try:
        return REQUESTS[kind].model_validate(proposal)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in ("proposal", *first.get("loc", ())))
        _invalid(field, first["msg"].removeprefix("Value error, "))


def check_fits(kind: str, key: GroupKey, req: BaseModel) -> None:
    """The proposal must be a fix for this group: the decode, trim text or yard strings come from the key."""
    if key.kind not in FITS[kind]:
        _invalid("kind", f"a {kind} can't fix a {key.kind} group")
    same = lambda a, b: name_key(a or "") == name_key(b or "")  # noqa: E731
    if kind == "decode_mapping":
        if not (same(req.make, key.make) and same(req.model, key.model)):
            _invalid("proposal.model", "the mapping is for a different decode than the group's")
        if req.series and not same(req.series, key.series):
            _invalid("proposal.series", "the series must be the group's, or none for any series")
    elif kind == "trim_mapping":
        if not (same(req.make, key.make) and same(req.trim, key.trim)):
            _invalid("proposal.trim", "the trim mapping is for a different make or trim text than the group's")
        if req.model and not same(req.model, key.model):
            _invalid("proposal.model", "the model must be the group's, or none for every model of the make")
    elif kind == "yard_rule":
        if ((req.raw_make or "").lower(), (req.raw_model or "").lower()) != ((key.make or "").lower(),
                                                                            (key.model or "").lower()):
            _invalid("proposal.raw_model", "the rule is for different yard strings than the group's")
        if req.source and req.source != key.source:
            _invalid("proposal.source", "the yard must be the group's, or none for every yard")


def group_vehicles(session: Session, key: GroupKey) -> int:
    """Open vehicles in the group now; 0 means it was fixed (or settled) some other way."""
    if key.kind == "trim":
        q = trims._unread().add_columns(func.count()).where(*trims._group_where(key.make, key.model, key.trim))
    else:
        q = open_discrepancies(select(func.count()).select_from(MappingDiscrepancy)
                               .join(Vehicle, Vehicle.id == MappingDiscrepancy.vehicle_id).where(key_filter(key)))
    return session.execute(q).scalar() or 0


def preview_of(eng, kind: str, key: GroupKey, req: BaseModel) -> dict:
    if kind == "decode_mapping":
        return fixes.preview_mapping(req, eng=eng)
    if kind == "trim_mapping":
        return trims.preview_trim_mapping_for(eng, req)
    if kind == "yard_rule":
        return fixes.preview_rule(req, eng=eng)
    with Session(eng[0]) as s:
        return {"vehicles": group_vehicles(s, key)}


def _apply(eng, kind: str, key: GroupKey, req: BaseModel, by: str) -> dict:
    if kind == "decode_mapping":
        return fixes.save_mapping(eng, req, by)
    if kind == "trim_mapping":
        return trims.save_trim_mapping(eng, req, by)
    if kind == "yard_rule":
        return fixes.save_rule(eng, req, by)
    with Session(eng[0]) as s:
        n = discrepancies.set_status(s, key, ignore=True)
        s.commit()
    return {"updated": n}


def _changes_nothing(kind: str, preview: dict) -> str | None:
    """Why a preview shows the fix would do nothing useful (filing refuses it), else None."""
    if not preview.get("vehicles"):
        return "it covers no open vehicles"
    if kind in ("decode_mapping", "yard_rule") and not preview.get("wouldMatch"):
        return "the preview matches none of the vehicles it covers"
    if kind == "trim_mapping" and preview.get("wider"):
        return f"{preview['wider']} vehicles would get more candidates: it overrides a reading that worked"
    return None


def creator(s: FixSuggestion, user: str, edited: bool) -> str:
    """created_by for a fix made from a suggestion. Deliberately not the MCP's "agent:" prefix: once a person
    approved it, it is theirs, and agents can't delete it."""
    return f"agent-suggested:{s.model} ({'edited' if edited else 'approved'} by {user})"[:100]


def out(s: FixSuggestion) -> dict:
    return {"id": s.id, "kind": s.kind, "key": s.group_key, "proposal": s.proposal, "preview": s.preview,
            "rationale": s.rationale, "model": s.model, "prompt": s.prompt, "filedBy": s.filed_by,
            "filedAt": s.filed_at.isoformat(), "status": s.status, "reviewedBy": s.reviewed_by,
            "reviewedAt": s.reviewed_at.isoformat() if s.reviewed_at else None, "rejectReason": s.reject_reason,
            "final": s.final, "result": s.result}


# ── filing ─────────────────────────────────────────────────────────────────────────────────────────

def file_suggestion(eng, kind: str, key: GroupKey, proposal: dict, rationale: str | None, model: str,
                    filed_by: str, prompt: str | None = None) -> dict:
    """Check and store a suggestion with the preview it was made under. Refused when the group already has one
    waiting, when the same fix was rejected for it before, or when the preview says it would do nothing."""
    if kind not in REQUESTS:
        _invalid("kind", f"kind must be one of {sorted(REQUESTS)}")
    req = parse(kind, proposal)
    check_fits(kind, key, req)
    proposal = req.model_dump(mode="json")
    gref, pref = group_ref(key), _hash(kind, key.model_dump(), proposal)
    with Session(eng[0]) as s:
        if not group_vehicles(s, key):
            _invalid("key", "this group has no open vehicles (it may have just been fixed)")
        waiting = s.execute(select(FixSuggestion.id).where(FixSuggestion.group_ref == gref,
                                                           FixSuggestion.status == PENDING)).scalar()
        if waiting:
            _invalid("key", f"suggestion {waiting} is already waiting for review for this group", 409)
        if s.execute(select(FixSuggestion.id).where(FixSuggestion.proposal_ref == pref,
                                                    FixSuggestion.status == REJECTED)).scalar():
            _invalid("proposal", "this exact fix was rejected for this group before; don't suggest it again")
    preview = preview_of(eng, kind, key, req)
    if why := _changes_nothing(kind, preview):
        _invalid("proposal", f"not filed: {why}")
    with Session(eng[0]) as s:
        row = FixSuggestion(kind=kind, group_key=key.model_dump(), group_ref=gref, proposal_ref=pref,
                            proposal=proposal, preview=preview, rationale=(rationale or "")[:2000] or None,
                            model=model[:100], prompt=prompt, filed_by=filed_by[:100], filed_at=_now(),
                            status=PENDING)
        s.add(row)
        s.commit()
        return out(row)


# ── reading ────────────────────────────────────────────────────────────────────────────────────────

def mark_stale(session: Session) -> int:
    """Pending suggestions whose group has emptied (fixed or settled another way) go stale."""
    n = 0
    for row in session.execute(select(FixSuggestion).where(FixSuggestion.status == PENDING)).scalars():
        if not group_vehicles(session, GroupKey(**row.group_key)):
            row.status, row.reviewed_at = STALE, _now()
            n += 1
    return n


VIEWS = {"pending": (PENDING,), "reviewed": (APPROVED, EDITED), "rejected": (REJECTED,), "stale": (STALE,)}


def list_suggestions(eng, view: str = "pending", kind: str | None = None, limit: int = 200) -> dict:
    if view not in VIEWS:
        _invalid("view", f"view must be one of {sorted(VIEWS)}")
    with Session(eng[0]) as s:
        mark_stale(s)
        s.commit()
        counts = dict(s.execute(select(FixSuggestion.status, func.count()).group_by(FixSuggestion.status)).all())
        q = select(FixSuggestion).where(FixSuggestion.status.in_(VIEWS[view]))
        if kind:
            q = q.where(FixSuggestion.kind == kind)
        order = FixSuggestion.filed_at if view == "pending" else FixSuggestion.reviewed_at.desc()
        rows = s.execute(q.order_by(order, FixSuggestion.id).limit(limit)).scalars().all()
        return {"suggestions": [out(r) for r in rows],
                "counts": {v: sum(counts.get(st, 0) for st in sts) for v, sts in VIEWS.items()}}


def pending_for(session: Session, key: GroupKey) -> dict | None:
    row = session.execute(select(FixSuggestion).where(FixSuggestion.group_ref == group_ref(key),
                                                      FixSuggestion.status == PENDING)).scalars().first()
    return out(row) if row else None


def _pending(s: Session, sid: int) -> FixSuggestion:
    row = s.get(FixSuggestion, sid)
    if row is None:
        raise HTTPException(404, "suggestion not found")
    if row.status != PENDING:
        _invalid("status", f"suggestion {sid} is already {row.status}", 409)
    return row


# ── routes ─────────────────────────────────────────────────────────────────────────────────────────

@router.get("/suggestions")
def get_suggestions(view: str = "pending", kind: str | None = None, eng=Depends(engines)):
    return list_suggestions(eng, view, kind)


@router.get("/suggestions/{sid}")
def get_suggestion(sid: int, eng=Depends(engines)):
    with Session(eng[0]) as s:
        row = s.get(FixSuggestion, sid)
        if row is None:
            raise HTTPException(404, "suggestion not found")
        return out(row)


@router.post("/suggestions/{sid}/preview")
def live_preview(sid: int, eng=Depends(engines)):
    """The proposal's preview against today's data (the stored one may be days old)."""
    with Session(eng[0]) as s:
        row = _pending(s, sid)
        key = GroupKey(**row.group_key)
        if not group_vehicles(s, key):
            row.status, row.reviewed_at = STALE, _now()
            s.commit()
            _invalid("status", "this group has no open vehicles any more: the suggestion is stale", 409)
        kind, proposal = row.kind, row.proposal
    return preview_of(eng, kind, key, parse(kind, proposal))


class ApproveRequest(BaseModel):
    preview: dict                            # the live preview the reviewer saw; must still hold
    kind: Kind | None = None                 # a tweak may change the kind (e.g. ignore -> mapping) ...
    proposal: dict | None = None             # ... and the proposal; both default to the suggestion's


@router.post("/suggestions/{sid}/approve")
def approve(sid: int, body: ApproveRequest, request: Request, eng=Depends(engines)):
    """Make the fix, as a manual one would be made, and record who approved it and whether they changed it."""
    with Session(eng[0]) as s:
        row = _pending(s, sid)
        key = GroupKey(**row.group_key)
        kind = body.kind or row.kind
        req = parse(kind, body.proposal if body.proposal is not None else row.proposal)
    check_fits(kind, key, req)
    final = req.model_dump(mode="json")
    edited = kind != row.kind or final != row.proposal
    live = preview_of(eng, kind, key, req)
    if live != body.preview:
        _invalid("preview", "the numbers changed since you looked; check the new preview and approve again", 409)
    user = who(request)
    result = _apply(eng, kind, key, req, creator(row, user, edited))
    with Session(eng[0]) as s:
        row = _pending(s, sid)
        row.status, row.reviewed_by, row.reviewed_at = EDITED if edited else APPROVED, user[:100], _now()
        row.final = {"kind": kind, "proposal": final, "preview": live} if edited else None
        row.result = result
        s.commit()
        return out(row)


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.post("/suggestions/{sid}/reject")
def reject(sid: int, body: RejectRequest, request: Request, eng=Depends(engines)):
    with Session(eng[0]) as s:
        row = _pending(s, sid)
        row.status, row.reviewed_by, row.reviewed_at = REJECTED, who(request)[:100], _now()
        row.reject_reason = (body.reason or "").strip() or None
        s.commit()
        return out(row)
