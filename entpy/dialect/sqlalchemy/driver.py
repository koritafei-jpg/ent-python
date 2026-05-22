"""SQLAlchemy 同步驱动。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class SQLAlchemyDriver:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> SQLAlchemyDriver:
        return cls(create_engine(url, **kwargs))

    def dialect(self) -> str:
        return self._engine.dialect.name

    @contextmanager
    def session(self):
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def exec(self, session: Session, stmt: Any, params: dict | None = None) -> Any:
        result = session.execute(stmt, params or {})
        return result

    def query(self, session: Session, stmt: Any, params: dict | None = None) -> Any:
        return session.execute(stmt, params or {}).mappings().all()

    @property
    def engine(self) -> Engine:
        return self._engine
