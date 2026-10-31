# matching-v2 prod promotion rolled out new code before its migrations: the VIN worker failed with UndefinedColumn

**Date:** 2026-10-31  
**Component:** the one-off promotion script (not in the repo); `junkyard-platform/db/alembic/versions/0007_trim_mappings.py`–`0009`; `pipeline/worker.py`  
**Severity:** Medium: prod's vin-resolver failed every batch for about two minutes (04:47–04:49 UTC); failed batches leave their vehicles queued, so nothing was lost. ⚠ Whether the admin API errored for users in that window is unrecorded (no traffic was checked).

---

## Observed symptom

After the promotion pushed `admin-api` / `vin-resolver` `sha-e088826337e7` to prod, the requeue step failed with
`psycopg2.errors.UndefinedColumn: column "car_id_match_steps" of relation "vehicles" does not exist`, and the
worker logged the same error on every batch (`SELECT ... vehicles.car_id_match_steps ...`). `alembic current` on
prod then said `0006`: migrations 0007–0009 had never run.

## Root cause

The script's migration step was

```
kubectl -n gyopart exec "$P" -- sh -c 'cd /app/db && alembic current 2>/dev/null | tail -1 && alembic upgrade head 2>&1 | grep Running; alembic current 2>/dev/null | tail -1'
```

run in the *old* vin-resolver pod after `kubectl cp` of the three migration files into it. It printed nothing at all:
even `alembic current`, which prints the revision on stdout, failed there; its error went to `/dev/null`, the
upgrade's went through `grep Running`, and `;` let the shell exit 0. The script (`set -e`) went on to push the
image pins. ⚠ Why Alembic failed in the old pod is unverified: the pod was replaced minutes later.

## Fix

`alembic upgrade head` in the *new* pod, unfiltered: 0006 → 0009 in one go; the worker's next batch succeeded and
the `vin_candidates` requeue (59,076 vehicles) finished with no further errors.

## What to do next time

- Run migrations where the migration files ship (an image that has them), not by copying files into an old pod.
- Never filter or discard Alembic's output in a deploy step, and check the result: `alembic current` must print the
  head revision before any image that needs it is pinned.
- Order stays: migrate, *verify*, then pin.
