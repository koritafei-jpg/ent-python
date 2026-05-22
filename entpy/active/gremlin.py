"""Gremlin 存储辅助（清图、建连）。"""

from __future__ import annotations

from entpy.active.context import get_client


def ensure_connection() -> None:
    """确保 Gremlin 远程连接已建立。"""
    client = get_client()
    if client._registry.storage != "gremlin":
        raise RuntimeError("ensure_connection() 仅用于 storage='gremlin'")
    client._driver._ensure()


def clear_graph(*labels: str) -> None:
    """按顶点标签清空图（仅 Gremlin 存储）。"""
    client = get_client()
    if client._registry.storage != "gremlin":
        raise RuntimeError("clear_graph() 仅用于 storage='gremlin'")
    from entpy.dialect.gremlin import graph_ops

    with client._driver.session() as session:
        graph_ops.clear_vertices(session.g, list(labels))
