import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from parts_interchange_common.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables that exist in the deployed database but not in the models. car_categories is empty and
# unused (2026-10-11); ignored here so autogenerate never proposes dropping it unasked.
UNMANAGED_TABLES = {"car_categories"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in UNMANAGED_TABLES)


def _get_url() -> str:
    url = os.environ.get("PARTS_INTERCHANGE_DATABASE_URL")
    if not url:
        raise RuntimeError("PARTS_INTERCHANGE_DATABASE_URL environment variable is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
