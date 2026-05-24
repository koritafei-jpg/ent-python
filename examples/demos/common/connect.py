"""Demo 数据库连接：通过 entpy 连接钩子（config / env / 自定义）。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

from entpy.active import async_bind, bind
from entpy.runtime.connect import (
    ConnectRequest,
    callable_connection_hook,
    load_config,
    register_connection_hook,
    resolve_connection,
)
from entpy.schema.base import Schema

_DEMOS_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = _DEMOS_ROOT / "config"


def config_file(name: str) -> str:
    """``examples/demos/config`` 下 JSON 配置路径。"""
    return str(CONFIG_DIR / name)


def sqlite_memory_config() -> dict[str, Any]:
    return {"dsn": "sqlite:///:memory:", "storage": "sql"}


def gremlin_config(dsn: str | None = None) -> dict[str, Any]:
    """Gremlin 连接配置；DSN 优先参数，其次 ``ENTPY_DSN`` / ``ENTPY_GREMLIN_URL``。"""
    url = (
        dsn
        or os.environ.get("ENTPY_DSN")
        or os.environ.get("ENTPY_GREMLIN_URL")
        or "ws://localhost:8182/gremlin"
    )
    return {"dsn": url, "storage": "gremlin"}


def _connection_source() -> str | None:
    """``ENTPY_DEMO_SOURCE=env`` 时使用环境变量钩子（``ENTPY_DSN`` 等）。"""
    src = os.environ.get("ENTPY_DEMO_SOURCE", "").strip().lower()
    return src if src in ("env", "config") else None


@contextmanager
def demo_bind(
    schemas: list[type[Schema]],
    *,
    config: dict[str, Any] | str | None = None,
    hooks: list[Any] | None = None,
    **engine_kw: Any,
) -> Iterator[Any]:
    """绑定 SQL demo 库（默认 ``config/sqlite-memory.json`` → ``ConfigConnectionHook``）。"""
    source = _connection_source()
    if source == "env":
        with bind(
            schemas=schemas,
            source="env",
            hooks=hooks,
            **engine_kw,
        ) as client:
            yield client
        return

    cfg = config if config is not None else config_file("sqlite-memory.json")
    with bind(
        config=cfg,
        schemas=schemas,
        hooks=hooks,
        **engine_kw,
    ) as client:
        yield client


@contextmanager
def demo_bind_gremlin(
    schemas: list[type[Schema]],
    *,
    config: dict[str, Any] | str | None = None,
    hooks: list[Any] | None = None,
) -> Iterator[Any]:
    """绑定 Gremlin demo（默认 ``config/gremlin-local.json`` 或 ``gremlin_config()``）。"""
    source = _connection_source()
    if source == "env":
        with bind(
            schemas=schemas,
            source="env",
            storage="gremlin",
            hooks=hooks,
        ) as client:
            yield client
        return

    cfg = config if config is not None else config_file("gremlin-local.json")
    with bind(
        config=cfg,
        schemas=schemas,
        hooks=hooks,
    ) as client:
        yield client


@asynccontextmanager
async def demo_async_bind(
    schemas: list[type[Schema]],
    *,
    config: dict[str, Any] | str | None = None,
    hooks: list[Any] | None = None,
    **engine_kw: Any,
) -> AsyncIterator[Any]:
    """异步 SQL demo（``config`` 中可设 ``\"async\": true``）。"""
    source = _connection_source()
    if source == "env":
        async with async_bind(
            schemas=schemas,
            source="env",
            hooks=hooks,
            **engine_kw,
        ) as client:
            yield client
        return

    cfg: dict[str, Any] | str
    if config is not None:
        cfg = config
    else:
        cfg = {**load_config(config_file("sqlite-memory.json")), "async": True}
    async with async_bind(
        config=cfg,
        schemas=schemas,
        hooks=hooks,
        **engine_kw,
    ) as client:
        yield client


def register_demo_connection_hook(
    match_fn: Any,
    open_fn: Any,
    *,
    prepend: bool = True,
) -> None:
    """注册自定义连接钩子（各 demo 可覆盖默认 config/env 行为）。"""
    register_connection_hook(
        callable_connection_hook(match_fn, open_fn),
        prepend=prepend,
    )


def open_demo_client(
    schemas: list[type[Schema]],
    *,
    config: dict[str, Any] | str | None = None,
    hooks: list[Any] | None = None,
) -> Any:
    """不经 ``with``，直接 ``resolve_connection``（适合脚本外手动管理生命周期）。"""
    source = _connection_source()
    if source == "env":
        return resolve_connection(
            ConnectRequest(schemas=schemas, source="env", runtime_hooks=hooks)
        )
    cfg = config if config is not None else config_file("sqlite-memory.json")
    if isinstance(cfg, str):
        merged = load_config(cfg)
    else:
        merged = dict(cfg)
    return resolve_connection(
        ConnectRequest(
            schemas=schemas,
            config=merged,
            dsn=merged.get("dsn"),
            storage=str(merged.get("storage", "sql")),
            runtime_hooks=hooks,
        )
    )
