from __future__ import annotations

from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from src.config import settings
        _engine = create_engine(settings.parts_database_url, pool_pre_ping=True)
    return _engine


def get_db() -> Generator[Session, None, None]:
    with Session(_get_engine()) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


DbDep = Annotated[Session, Depends(get_db)]
