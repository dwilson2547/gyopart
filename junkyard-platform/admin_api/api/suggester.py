"""The fix suggester's runs (matching-v2-design §3.4): recent runs, and "run now".

The work never runs in the web process: run now creates a one-off Job from the suggester's CronJob (what
`kubectl create job --from=cronjob/fix-suggester` does), with the trigger set to manual. Without cluster access, or
where the chart doesn't deploy the CronJob, run now says it's unavailable and the history still shows.
"""
from __future__ import annotations

import datetime
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from junkyard_common.models import SuggesterAttempt, SuggesterRun

from .common import engines

router = APIRouter(prefix="/api", tags=["suggester"])

CRONJOB = "fix-suggester"
STUCK = datetime.timedelta(hours=3)        # a "running" run older than this died without saying so
_SA_NAMESPACE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


class Unavailable(Exception):
    pass


def _namespace() -> str:
    if ns := os.environ.get("SCRAPEJOB_NAMESPACE"):
        return ns
    try:
        return open(_SA_NAMESPACE).read().strip()
    except OSError as exc:
        raise Unavailable("not running in the cluster") from exc


def _batch():
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise Unavailable("the kubernetes client isn't installed") from exc
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except Exception as exc:
            raise Unavailable("no cluster access") from exc
    return client, client.BatchV1Api()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def run_out(r: SuggesterRun) -> dict:
    return {"id": r.id, "trigger": r.trigger, "startedAt": r.started_at.isoformat(),
            "finishedAt": r.finished_at.isoformat() if r.finished_at else None, "status": r.status,
            "counts": r.counts or {}, "error": r.error}


def attempt_out(a: SuggesterAttempt | None) -> dict | None:
    if a is None:
        return None
    return {"at": a.at.isoformat(), "outcome": a.outcome, "reason": a.reason, "model": a.model, "prompt": a.prompt,
            "vehicles": a.vehicles, "suggestionId": a.suggestion_id}


def last_attempt(session: Session, group_ref: str) -> dict | None:
    return attempt_out(session.execute(select(SuggesterAttempt).where(SuggesterAttempt.group_ref == group_ref)
                                       .order_by(SuggesterAttempt.id.desc()).limit(1)).scalars().first())


def _running(s: Session) -> SuggesterRun | None:
    return s.execute(select(SuggesterRun).where(SuggesterRun.status == "running",
                                                SuggesterRun.started_at > _now() - STUCK)
                     .order_by(SuggesterRun.id.desc()).limit(1)).scalars().first()


@router.get("/suggester")
def status(eng=Depends(engines)):
    with Session(eng[0]) as s:
        runs = s.execute(select(SuggesterRun).order_by(SuggesterRun.id.desc()).limit(10)).scalars().all()
        running = _running(s)
    out = {"runs": [run_out(r) for r in runs], "running": running is not None, "runNow": True, "schedule": None}
    try:
        _, api = _batch()
        cj = api.read_namespaced_cron_job(CRONJOB, _namespace())
        out["schedule"] = cj.spec.schedule
    except Unavailable as exc:
        out.update(runNow=False, reason=str(exc))
    except Exception as exc:     # the chart doesn't deploy the CronJob here, or RBAC says no
        out.update(runNow=False, reason=f"no {CRONJOB} CronJob here ({getattr(exc, 'status', type(exc).__name__)})")
    return out


@router.post("/suggester/run")
def run_now(eng=Depends(engines)):
    with Session(eng[0]) as s:
        if _running(s) is not None:
            raise HTTPException(409, "a suggester run is already going")
    try:
        client, api = _batch()
        ns = _namespace()
        cj = api.read_namespaced_cron_job(CRONJOB, ns)
    except Unavailable as exc:
        raise HTTPException(503, f"run now is unavailable: {exc}") from None
    except Exception:
        raise HTTPException(503, f"run now is unavailable: no {CRONJOB} CronJob here") from None
    spec = cj.spec.job_template.spec
    for c in spec.template.spec.containers:
        c.args = ["--trigger", "manual"]
    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=f"{CRONJOB}-manual-{int(time.time())}", namespace=ns,
                                     labels={"app": CRONJOB, "trigger": "manual"},
                                     annotations={"cronjob.kubernetes.io/instantiate": "manual"}),
        spec=spec)
    api.create_namespaced_job(ns, job)
    return {"started": job.metadata.name}
