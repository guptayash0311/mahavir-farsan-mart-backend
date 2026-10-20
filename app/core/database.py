from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

_engine: Engine | None = None


class Base(DeclarativeBase):
    pass


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        from app.core.config import get_settings

        _engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
    return _engine


def get_session() -> Generator[Session, None, None]:
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()
