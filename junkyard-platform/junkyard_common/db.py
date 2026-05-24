import os

from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import Session


def get_engine(url: str | None = None):
    database_url = url or os.environ["JUNKYARD_DATABASE_URL"]
    return _create_engine(database_url)


def get_session(engine) -> Session:
    return Session(engine)
