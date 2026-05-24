"""Active Record API：通过 bind() 上下文绑定数据库连接。"""

from __future__ import annotations

from typing import Any

from entpy.active.bind import (
    async_bind,
    async_bind_client,
    bind,
    bind_client,
    migrate,
    migrate_async,
)
from entpy.runtime.connect import (
    ConnectRequest,
    ConnectionHook,
    callable_connection_hook,
    clear_connection_hooks,
    config_from_env,
    load_config,
    register_connection_hook,
    resolve_connection,
)
from entpy.active.context import (
    get_async_client,
    get_bound_client,
    get_client,
    reject_async_module_api,
)
from entpy.active.entity import ActiveEntity
from entpy.active.gremlin import clear_graph, ensure_connection
from entpy.active.schema import ActiveSchema
from entpy.schema.base import Schema


def F(schema: type[Schema]):
    """当前 bind 下的谓词工厂 F（同步或异步）。"""
    return get_bound_client().F(schema)


def search(schema: type[Schema]):
    """当前 bind 下的检索构建器（混合 / BM25 / 语义）。"""
    return get_bound_client().search(schema)


def traverse(entity, edge: str | None = None):
    """边遍历（兼容写法）；推荐 ``entity.out('edge').out('edge').all()``。"""
    reject_async_module_api("traverse")
    return get_bound_client().traverse(entity, edge)


def update(schema: type[Schema], id: Any):
    """更新已有行（字段 ``set`` / 边 ``add`` / M2M ``set_edges``）。推荐 ``entity.edit()``。"""
    reject_async_module_api("update")
    return get_bound_client().update(schema, id)


__all__ = [
    "ActiveEntity",
    "ActiveSchema",
    "ConnectRequest",
    "ConnectionHook",
    "F",
    "async_bind",
    "async_bind_client",
    "bind",
    "bind_client",
    "callable_connection_hook",
    "clear_connection_hooks",
    "clear_graph",
    "config_from_env",
    "ensure_connection",
    "get_async_client",
    "get_bound_client",
    "get_client",
    "load_config",
    "migrate",
    "migrate_async",
    "register_connection_hook",
    "resolve_connection",
    "search",
    "traverse",
    "update",
]
