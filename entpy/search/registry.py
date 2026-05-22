"""从 Graph 构建的检索注册表。"""

from __future__ import annotations

from dataclasses import dataclass

from entpy.schema.base import Schema, SearchMixin
from entpy.schema.search import SearchConfig
from entpy.runtime.registry import Registry


@dataclass
class NodeSearchMeta:
    schema: type[Schema]
    config: SearchConfig
    text_columns: list[str]
    vector_column: str | None


class SearchRegistry:
    def __init__(self, nodes: dict[type[Schema], NodeSearchMeta]) -> None:
        self._nodes = nodes

    @classmethod
    def from_registry(cls, registry: Registry) -> SearchRegistry:
        nodes: dict[type[Schema], NodeSearchMeta] = {}
        for schema, node in registry.nodes.items():
            if not issubclass(schema, SearchMixin):
                continue
            cfg = schema.search_config()
            if cfg is None:
                continue
            text_cols = []
            for f in node.fields:
                if f.searchable and f.name in cfg.text_fields:
                    text_cols.append(f.column)
            vec_col = None
            if cfg.vector_field:
                for f in node.fields:
                    if f.name == cfg.vector_field:
                        vec_col = f.column
            nodes[schema] = NodeSearchMeta(
                schema=schema,
                config=cfg,
                text_columns=text_cols,
                vector_column=vec_col,
            )
        return cls(nodes)

    def get(self, schema: type[Schema]) -> NodeSearchMeta:
        return self._nodes[schema]

    def has(self, schema: type[Schema]) -> bool:
        return schema in self._nodes
