"""Active Record API：通过 bind() 上下文绑定数据库连接。"""

from entpy.active.bind import async_bind, bind, migrate, migrate_async
from entpy.active.context import get_async_client, get_bound_client, get_client
from entpy.active.entity import ActiveEntity
from entpy.active.gremlin import clear_graph, ensure_connection
from entpy.active.schema import ActiveSchema
from entpy.schema.base import Schema


def F(schema: type[Schema]):
    """当前 bind 下的谓词工厂 F（同步或异步）。"""
    return get_bound_client().F(schema)


def search(schema: type[Schema]):
    """当前 bind 下的检索构建器（混合 / BM25 / 语义）。"""
    return get_client().search(schema)


def traverse(entity, edge: str | None = None):
    """边遍历（兼容写法）；推荐 ``entity.out('edge').out('edge').all()``。"""
    return get_client().traverse(entity, edge)


def update(schema: type[Schema], id: int):
    """更新已有行（例如关联边）。"""
    return get_client().update(schema, id)


__all__ = [
    "ActiveEntity",
    "ActiveSchema",
    "F",
    "async_bind",
    "bind",
    "clear_graph",
    "ensure_connection",
    "get_async_client",
    "get_bound_client",
    "get_client",
    "migrate",
    "migrate_async",
    "search",
    "traverse",
    "update",
]
