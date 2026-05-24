from __future__ import annotations

from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from parts_interchange_common.models import Base

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from src.config import settings
        _engine = create_engine(settings.parts_database_url, pool_pre_ping=True)
    return _engine


def create_tables() -> None:
    Base.metadata.create_all(_get_engine())


def get_db() -> Generator[Session, None, None]:
    with Session(_get_engine()) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


DbDep = Annotated[Session, Depends(get_db)]
