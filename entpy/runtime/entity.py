"""实体结果封装。"""

from __future__ import annotations

from typing import Any

from entpy.schema.base import Schema


class Entity:
    def __init__(
        self,
        schema: type[Schema],
        data: dict[str, Any],
        client: Any = None,
    ) -> None:
        self._schema = schema
        self._data = dict(data)
        self._client = client
        edges = self._data.pop("_edges", None)
        if edges:
            self._edges = edges
        else:
            self._edges = {}

    @property
    def id(self) -> Any:
        return self._data.get("id")

    def _peer_schema_for_edge(self, edge_name: str) -> type[Schema] | None:
        client = self._client
        if client is None:
            try:
                from entpy.active.context import get_bound_client

                client = get_bound_client()
            except RuntimeError:
                return None
        re = client._registry.resolve_edge(self._schema, edge_name)
        if re is None:
            return None
        return re.peer.schema_type

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._edges:
            peer = self._peer_schema_for_edge(name) or self._schema
            return [Entity(peer, dict(e), self._client) for e in self._edges[name]]
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if not k.startswith("_")}

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        from entpy.active.context import get_bound_client

        return get_bound_client()

    def out(self, edge_name: str) -> Any:
        """从当前实体出发的边遍历链：``alice.out('knows').out('knows').all()``。

        同步 bind 下 ``.all()`` 为同步；async_bind 下请 ``await .all()``。
        """
        from entpy.runtime.driver_util import is_async_sql_driver
        from entpy.runtime.traverse import AsyncTraverseChain, TraverseChain

        client = self._require_client()
        if is_async_sql_driver(client):
            return AsyncTraverseChain(client, self, [edge_name])
        return TraverseChain(client, self, [edge_name])

    def get_edge(self, name: str) -> list[Entity]:
        raw = self._edges.get(name, [])
        peer = self._peer_schema_for_edge(name) or self._schema
        return [Entity(peer, e, self._client) for e in raw]
