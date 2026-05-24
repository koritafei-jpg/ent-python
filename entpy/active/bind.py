"""bind / async_bind 上下文管理器，绑定同步或异步 Client。"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator, Literal

from entpy.runtime.async_client import AsyncClient
from entpy.runtime.client import Client
from entpy.schema.base import Schema

Lifecycle = Literal["request", "app"]


@contextmanager
def bind(
    dsn: str,
    *,
    schemas: list[type[Schema]],
    storage: str = "sql",
    observer_packages: list[str] | None = None,
    hooks: list[Any] | None = None,
    ctx: dict[str, Any] | None = None,
    lifecycle: Lifecycle = "request",
    **engine_kw: Any,
) -> Iterator[Client]:
    """绑定同步 Client；块内使用 User.create / User.query。

    ``lifecycle="request"``（默认）：退出时释放连接，适合脚本与测试。
    ``lifecycle="app"``：仅解除 ContextVar，连接由 ``Client.close()`` 释放，适合长驻进程。
    """
    client = Client.open(
        dsn,
        schemas=schemas,
        storage=storage,
        observer_packages=observer_packages,
        ctx=ctx,
        **engine_kw,
    )
    if hooks:
        client._hooks = list(hooks) + list(client._hooks)
    with client.scope():
        yield client
    if lifecycle == "request":
        client.close()


@asynccontextmanager
async def async_bind(
    dsn: str,
    *,
    schemas: list[type[Schema]],
    storage: str = "sql",
    observer_packages: list[str] | None = None,
    hooks: list[Any] | None = None,
    ctx: dict[str, Any] | None = None,
    lifecycle: Lifecycle = "request",
    **engine_kw: Any,
) -> AsyncIterator[AsyncClient]:
    """绑定异步 Client；块内使用 await client.create(...).save()。"""
    client = AsyncClient.open(
        dsn,
        schemas=schemas,
        storage=storage,
        observer_packages=observer_packages,
        ctx=ctx,
        **engine_kw,
    )
    if hooks:
        client._hooks = list(hooks) + list(client._hooks)
    async with client.ascope():
        yield client
    if lifecycle == "request":
        await client.aclose()


def migrate() -> None:
    """DDL：为当前同步 bind 建表。"""
    from entpy.active.context import get_client

    get_client().migrate()


async def migrate_async() -> None:
    """DDL：为当前异步 bind 建表。"""
    from entpy.active.context import get_async_client

    await get_async_client().migrate()
