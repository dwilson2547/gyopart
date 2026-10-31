"""Client for the cluster's GPU job queue: submit a batch of chat jobs, wait for all of them, return replies in order.

Configured by SUGGESTER_GPU_URL and SUGGESTER_GPU_TOKEN (from a Secret; see the chart's fix-suggester CronJob).
"""
from __future__ import annotations

import os
import time

import httpx

MAX_BATCH = 1000          # the queue's limit per submit


class GpuUnavailable(Exception):
    pass


class GpuClient:
    def __init__(self, url: str, token: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.url, self.headers, self.timeout = url.rstrip("/"), {"Authorization": f"Bearer {token}"}, timeout
        self.transport = transport          # tests

    @classmethod
    def from_env(cls) -> "GpuClient":
        url, token = os.environ.get("SUGGESTER_GPU_URL"), os.environ.get("SUGGESTER_GPU_TOKEN")
        if not url or not token:
            raise GpuUnavailable("SUGGESTER_GPU_URL and SUGGESTER_GPU_TOKEN aren't set")
        return cls(url, token)

    def run(self, model: str, inputs: list[dict], deadline_seconds: int = 3600, wait_seconds: float = 3600,
            poll_seconds: float = 5.0) -> list[dict]:
        """One job per input. Returns, in input order, {"result": ...} or {"error": "..."}; raises GpuUnavailable
        when the queue can't be reached or the jobs don't finish in wait_seconds."""
        out: list[dict] = []
        with httpx.Client(timeout=self.timeout, headers=self.headers, transport=self.transport) as http:
            for i in range(0, len(inputs), MAX_BATCH):
                try:
                    r = http.post(f"{self.url}/v1/jobs", json={"model": model, "inputs": inputs[i:i + MAX_BATCH],
                                                                "deadline_seconds": deadline_seconds})
                    r.raise_for_status()
                except httpx.HTTPError as exc:
                    raise GpuUnavailable(f"submit failed: {exc}") from exc
                out += self._wait(http, r.json()["batch_id"], wait_seconds, poll_seconds)
        return out

    def _wait(self, http: httpx.Client, batch_id: str, wait_seconds: float, poll_seconds: float) -> list[dict]:
        until = time.monotonic() + wait_seconds
        while True:
            try:
                r = http.get(f"{self.url}/v1/batches/{batch_id}")
                r.raise_for_status()
                b = r.json()
            except httpx.HTTPError as exc:
                raise GpuUnavailable(f"polling batch {batch_id} failed: {exc}") from exc
            if b["complete"]:
                return [{"result": j["result"]} if j["status"] == "done" else {"error": j.get("error") or j["status"]}
                        for j in b["jobs"]]
            if time.monotonic() > until:
                raise GpuUnavailable(f"batch {batch_id} not finished after {wait_seconds:.0f} s")
            time.sleep(poll_seconds)
