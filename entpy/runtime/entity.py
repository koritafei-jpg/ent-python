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
        edges = data.get("_edges")
        if edges:
            self._edges = edges
        else:
            self._edges = {}

    @property
    def id(self) -> Any:
        return self._data.get("id")

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._edges:
            return [Entity(self._schema, e, self._client) for e in self._edges[name]]
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if not k.startswith("_")}

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from entpy.active.context import get_client

            return get_client()
        except RuntimeError as e:
            raise RuntimeError(
                "边遍历需要 Client；请在 bind() 内使用，或确保实体来自 query/create"
            ) from e

    def out(self, edge_name: str) -> Any:
        """从当前实体出发的边遍历链：``alice.out('knows').out('knows').all()``。"""
        from entpy.runtime.traverse import TraverseChain

        client = self._require_client()
        return TraverseChain(client, self, [edge_name])

    def get_edge(self, name: str) -> list[Entity]:
        raw = self._edges.get(name, [])
        peer_schema = None  # 需要时由 client 解析
        return [Entity(peer_schema or self._schema, e, self._client) for e in raw]
