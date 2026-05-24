"""事务级 SQL session 复用（ContextVar）。"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any

_tx_sync: ContextVar[Any] = ContextVar("entpy_tx_sync_session", default=None)
_tx_async: ContextVar[Any] = ContextVar("entpy_tx_async_session", default=None)


def get_tx_session(*, async_: bool = False) -> Any | None:
    return _tx_async.get() if async_ else _tx_sync.get()


@contextmanager
def sync_transaction(driver: Any):
    """在块内复用同一 ORM session，块末 commit；嵌套事务不支持。"""
    if _tx_sync.get() is not None:
        raise RuntimeError("nested entpy transactions are not supported")
    session = driver._session_factory()
    token = _tx_sync.set(session)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _tx_sync.reset(token)
        session.close()


@asynccontextmanager
async def async_transaction(driver: Any):
    if _tx_async.get() is not None:
        raise RuntimeError("nested entpy transactions are not supported")
    session = driver._session_factory()
    token = _tx_async.set(session)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        _tx_async.reset(token)
        await session.close()
