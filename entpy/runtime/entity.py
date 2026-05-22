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

    def get_edge(self, name: str) -> list[Entity]:
        raw = self._edges.get(name, [])
        peer_schema = None  # 需要时由 client 解析
        return [Entity(peer_schema or self._schema, e, self._client) for e in raw]
