"""bind / async_bind 上下文管理器，绑定同步或异步 Client。"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator, Literal

from entpy.runtime.async_client import AsyncClient
from entpy.runtime.client import Client
from entpy.runtime.connect import (
    ConnectRequest,
    ConnectionHook,
    resolve_connection,
)
from entpy.schema.base import Schema

Lifecycle = Literal["request", "app"]


def _parse_config(
    config: dict[str, Any] | str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if config is None:
        return None, None
    if isinstance(config, str):
        return None, config
    return config, None


def _make_request(
    *,
    schemas: list[type[Schema]],
    async_: bool,
    dsn: str | None,
    storage: str,
    config: dict[str, Any] | str | None,
    client: Any | None,
    owns_connection: bool,
    observer_packages: list[str] | None,
    hooks: list[Any] | None,
    ctx: dict[str, Any] | None,
    source: str | None,
    env_prefix: str,
    engine_kw: dict[str, Any],
) -> ConnectRequest:
    cfg_dict, cfg_path = _parse_config(config)
    return ConnectRequest(
        schemas=schemas,
        async_=async_,
        dsn=dsn,
        storage=storage,
        config=cfg_dict,
        config_path=cfg_path,
        env_prefix=env_prefix,
        client=client,
        owns_connection=owns_connection,
        observer_packages=observer_packages,
        runtime_hooks=hooks,
        ctx=ctx,
        engine_kw=engine_kw,
        source=source,
    )


@contextmanager
def bind(
    dsn: str | None = None,
    *,
    schemas: list[type[Schema]],
    storage: str = "sql",
    config: dict[str, Any] | str | None = None,
    client: Client | None = None,
    owns_connection: bool | None = None,
    connection_hooks: list[ConnectionHook] | None = None,
    source: str | None = None,
    env_prefix: str = "ENTPY_",
    observer_packages: list[str] | None = None,
    hooks: list[Any] | None = None,
    ctx: dict[str, Any] | None = None,
    lifecycle: Lifecycle = "request",
    **engine_kw: Any,
) -> Iterator[Client]:
    """绑定同步 Client；块内使用 ``User.create`` / ``User.query``。

    连接方式（按钩子链匹配，任选其一）：

    - **DSN**：``bind("sqlite:///:memory:", schemas=...)``
    - **配置**：``bind(config={"dsn": "..."}, ...)`` 或 ``bind(config="db.json", ...)``
    - **环境变量**：``bind(schemas=..., source="env")``（需 ``ENTPY_DSN``）
    - **已有 Client**：``bind(client=app_client, schemas=..., owns_connection=False)``
    - **自定义钩子**：``register_connection_hook`` 或 ``connection_hooks=[...]``

    ``lifecycle="request"``（默认）：退出时释放连接（``owns_connection=True`` 时）。
    ``lifecycle="app"``：仅解除 ContextVar，连接由 ``Client.close()`` 释放。
    """
    owns = owns_connection if owns_connection is not None else client is None
    request = _make_request(
        schemas=schemas,
        async_=False,
        dsn=dsn,
        storage=storage,
        config=config,
        client=client,
        owns_connection=owns,
        observer_packages=observer_packages,
        hooks=hooks,
        ctx=ctx,
        source=source,
        env_prefix=env_prefix,
        engine_kw=engine_kw,
    )
    resolved = resolve_connection(
        request,
        extra_hooks=connection_hooks,
        apply_runtime_hooks=False,
    )
    prev_hooks = list(resolved._hooks)
    if hooks:
        resolved._hooks = list(hooks) + prev_hooks
    try:
        with resolved.scope():
            yield resolved
    finally:
        resolved._hooks = prev_hooks
        if lifecycle == "request" and request.owns_connection:
            resolved.close()


@contextmanager
def bind_client(
    client: Client,
    *,
    ctx: dict[str, Any] | None = None,
    hooks: list[Any] | None = None,
    lifecycle: Lifecycle = "app",
    close_on_exit: bool = False,
) -> Iterator[Client]:
    """绑定已有 ``Client``（``with`` 钩子方式），适合应用级连接池。

    默认 ``lifecycle="app"`` 且不在退出时 ``close()``；测试可设 ``close_on_exit=True``。
    """
    prev_hooks = list(client._hooks)
    if hooks:
        client._hooks = list(hooks) + prev_hooks
    try:
        with client.scope(ctx=ctx):
            yield client
    finally:
        client._hooks = prev_hooks
        if lifecycle == "request" or close_on_exit:
            client.close()


@asynccontextmanager
async def async_bind(
    dsn: str | None = None,
    *,
    schemas: list[type[Schema]],
    storage: str = "sql",
    config: dict[str, Any] | str | None = None,
    client: AsyncClient | None = None,
    owns_connection: bool | None = None,
    connection_hooks: list[ConnectionHook] | None = None,
    source: str | None = None,
    env_prefix: str = "ENTPY_",
    observer_packages: list[str] | None = None,
    hooks: list[Any] | None = None,
    ctx: dict[str, Any] | None = None,
    lifecycle: Lifecycle = "request",
    **engine_kw: Any,
) -> AsyncIterator[AsyncClient]:
    """绑定异步 Client；连接解析方式与 ``bind`` 相同。"""
    owns = owns_connection if owns_connection is not None else client is None
    request = _make_request(
        schemas=schemas,
        async_=True,
        dsn=dsn,
        storage=storage,
        config=config,
        client=client,
        owns_connection=owns,
        observer_packages=observer_packages,
        hooks=hooks,
        ctx=ctx,
        source=source,
        env_prefix=env_prefix,
        engine_kw=engine_kw,
    )
    resolved = resolve_connection(
        request,
        extra_hooks=connection_hooks,
        apply_runtime_hooks=False,
    )
    prev_hooks = list(resolved._hooks)
    if hooks:
        resolved._hooks = list(hooks) + prev_hooks
    try:
        async with resolved.ascope():
            yield resolved
    finally:
        resolved._hooks = prev_hooks
        if lifecycle == "request" and request.owns_connection:
            await resolved.aclose()


@asynccontextmanager
async def async_bind_client(
    client: AsyncClient,
    *,
    ctx: dict[str, Any] | None = None,
    hooks: list[Any] | None = None,
    lifecycle: Lifecycle = "app",
    close_on_exit: bool = False,
) -> AsyncIterator[AsyncClient]:
    """绑定已有 ``AsyncClient``。"""
    prev_hooks = list(client._hooks)
    if hooks:
        client._hooks = list(hooks) + prev_hooks
    try:
        async with client.ascope(ctx=ctx):
            yield client
    finally:
        client._hooks = prev_hooks
        if lifecycle == "request" or close_on_exit:
            await client.aclose()


def migrate() -> None:
    """DDL：为当前同步 bind 建表。"""
    from entpy.active.context import get_client

    get_client().migrate()


async def migrate_async() -> None:
    """DDL：为当前异步 bind 建表。"""
    from entpy.active.context import get_async_client

    await get_async_client().migrate()
