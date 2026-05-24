"""驱动类型检测（避免 runtime 与 dialect 循环导入）。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


def is_async_sql_driver(client: Any) -> bool:
    from entpy.dialect.sqlalchemy.async_driver import AsyncSQLAlchemyDriver

    return isinstance(client._driver, AsyncSQLAlchemyDriver)


def is_async_client(client: Any) -> bool:
    from entpy.runtime.async_client import AsyncClient

    return isinstance(client, AsyncClient)


def is_gremlin_client(client: Any) -> bool:
    """当前 Client 是否使用 Gremlin 存储（避免多处重复 dialect 判断）。"""
    return client._driver.dialect() == "gremlin"


@contextmanager
def sync_sql_session(client: Any) -> Iterator[Any]:
    """检索等同步 API 用的 ORM session（AsyncClient 走 sync_engine）。"""
    if is_async_sql_driver(client):
        from sqlalchemy.orm import Session

        session = Session(client._driver.sync_engine)
        try:
            yield session
        finally:
            session.close()
    else:
        with client._driver.session() as session:
            yield session
