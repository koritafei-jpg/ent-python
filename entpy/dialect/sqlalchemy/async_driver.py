"""SQLAlchemy 2.x 异步驱动。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def _to_async_url(url: str) -> str:
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class AsyncSQLAlchemyDriver:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> AsyncSQLAlchemyDriver:
        return cls(create_async_engine(_to_async_url(url), **kwargs))

    def dialect(self) -> str:
        return self._engine.dialect.name

    @asynccontextmanager
    async def session(self):
        session: AsyncSession = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sync_engine(self):
        return self._engine.sync_engine
