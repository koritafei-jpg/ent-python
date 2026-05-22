"""bind / async_bind 上下文管理器，绑定同步或异步 Client。"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator

from entpy.active.context import (
    reset_async_client,
    reset_client,
    set_async_client,
    set_client,
)
from entpy.runtime.async_client import AsyncClient
from entpy.runtime.client import Client
from entpy.schema.base import Schema


@contextmanager
def bind(
    dsn: str,
    *,
    schemas: list[type[Schema]],
    storage: str = "sql",
    ctx: dict[str, Any] | None = None,
    **engine_kw: Any,
) -> Iterator[Client]:
    """绑定同步 Client；块内使用 User.create / User.query。"""
    client = Client.open(
        dsn, schemas=schemas, storage=storage, ctx=ctx, **engine_kw
    )
    token = set_client(client)
    try:
        yield client
    finally:
        reset_client(token)
        if storage == "gremlin":
            client._driver.close()


@asynccontextmanager
async def async_bind(
    dsn: str,
    *,
    schemas: list[type[Schema]],
    storage: str = "sql",
    ctx: dict[str, Any] | None = None,
    **engine_kw: Any,
) -> AsyncIterator[AsyncClient]:
    """绑定异步 Client；块内使用 await client.create(...).save()。"""
    client = AsyncClient.open(
        dsn, schemas=schemas, storage=storage, ctx=ctx, **engine_kw
    )
    token = set_async_client(client)
    try:
        yield client
    finally:
        reset_async_client(token)
        if storage == "gremlin":
            client._driver.close()


def migrate() -> None:
    """DDL：为当前同步 bind 建表。"""
    from entpy.active.context import get_client

    get_client().migrate()


async def migrate_async() -> None:
    """DDL：为当前异步 bind 建表。"""
    from entpy.active.context import get_async_client

    await get_async_client().migrate()
