"""The yard ScrapeJobs run by scrape-job-manager (web-scrapers/scrape-job-manager), for "re-scrape this yard".

A yard's job is found by the label gyopart.danwils.com/source=<vehicles.source> (set in the chart where the
names differ, e.g. picknpullsa -> picknpull-sa), else by name: the source with _ -> -. Run now is the same
annotation `kubectl annotate` writes; the operator picks it up on its next pass.

Everything here is optional: without cluster access the vehicle page just says re-scrape is unavailable.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache

GROUP, VERSION, PLURAL = "scrape.danwils.com", "v1alpha1", "scrapejobs"
# scrape_job_manager.constants.ANNOTATION_RUN_NOW (that package isn't installed in this image).
ANNOTATION_RUN_NOW = f"{GROUP}/run-now"
SOURCE_LABEL = "gyopart.danwils.com/source"
_SA_NAMESPACE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


class Unavailable(Exception):
    pass


@lru_cache(maxsize=1)
def _api():
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise Unavailable("the kubernetes client isn't installed") from exc
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except Exception as exc:  # no kubeconfig either
            raise Unavailable("no cluster access") from exc
    return client.CustomObjectsApi()


def namespace() -> str:
    if ns := os.environ.get("SCRAPEJOB_NAMESPACE"):
        return ns
    try:
        with open(_SA_NAMESPACE) as f:
            return f.read().strip()
    except OSError as exc:
        raise Unavailable("SCRAPEJOB_NAMESPACE is not set") from exc


def summarize(cr: dict) -> dict:
    spec, st = cr.get("spec") or {}, cr.get("status") or {}
    last = st.get("lastRun") or {}
    return {
        "name": cr["metadata"]["name"], "namespace": cr["metadata"]["namespace"],
        "phase": st.get("phase", "Pending"), "suspended": bool(spec.get("suspend")),
        "running": bool((st.get("currentRun") or {}).get("k8sJob")),
        "lastRun": {k: last.get(k) for k in ("result", "reason", "items", "finishedAt", "trigger")} if last else None,
        "lastSuccessAt": (st.get("lastSuccess") or {}).get("at"),
        "nextRunAt": st.get("nextRunAt"),
        # The annotation stays after a run; it's pending only until the operator records its value as handled.
        "runNowRequested": bool(asked := ((cr["metadata"].get("annotations")) or {}).get(ANNOTATION_RUN_NOW))
                           and asked != (st.get("handled") or {}).get("runNow"),
    }


def find(source: str) -> dict | None:
    """The ScrapeJob CR for a vehicles.source value, or None."""
    api, ns = _api(), namespace()
    try:
        labelled = api.list_namespaced_custom_object(GROUP, VERSION, ns, PLURAL,
                                                     label_selector=f"{SOURCE_LABEL}={source}")["items"]
        if labelled:
            return labelled[0]
        return api.get_namespaced_custom_object(GROUP, VERSION, ns, PLURAL, source.replace("_", "-"))
    except Exception as exc:
        if getattr(exc, "status", None) == 404:
            return None
        raise Unavailable(f"the cluster refused: {getattr(exc, 'reason', exc)}") from exc


def run_now(name: str) -> None:
    try:
        _api().patch_namespaced_custom_object(GROUP, VERSION, namespace(), PLURAL, name,
                                              {"metadata": {"annotations": {ANNOTATION_RUN_NOW: str(int(time.time()))}}})
    except Unavailable:
        raise
    except Exception as exc:
        raise Unavailable(f"the cluster refused the run: {getattr(exc, 'reason', exc)}") from exc
