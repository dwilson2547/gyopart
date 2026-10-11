# parts_interchange migrations

Alembic for the `parts_interchange` schema. The models (schema authority) are in
`parts_interchange_common/models.py`, published as `dwilson-parts-interchange-common`.

```bash
pip install alembic -e ..                  # from this directory; installs the models package
export PARTS_INTERCHANGE_DATABASE_URL=postgresql://<owner>:<pw>@<host>:5432/parts_interchange
alembic current                            # where a database is
alembic upgrade head                       # apply pending revisions
alembic check                              # models vs database: "No new upgrade operations detected."
```

- Run as the role that owns the tables (`gyopart_dev` on dev, `gyopart` on prod) — adding constraints
  needs ownership.
- `0001_baseline` is empty: databases that existed before Alembic (dev and prod, loaded by
  parts-loader-v2) are first stamped with `alembic stamp 0001_baseline`, then upgraded.
- `car_categories` exists in the deployed databases but not in the models; `env.py` ignores it so
  autogenerate never proposes dropping it.
- New revision: change the models, then `alembic revision --autogenerate -m "..."` against a database
  at head, and read the result before committing.
