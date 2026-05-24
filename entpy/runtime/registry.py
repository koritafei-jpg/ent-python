"""运行时注册表：Graph + SQL 表 + 谓词。"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Table

from entpy.ir.graph import Graph, ResolvedEdge, build_graph
from entpy.ir.descriptor import NodeDescriptor
from entpy.dialect.sqlalchemy.metadata import tables_for_graph
from entpy.schema.base import Schema
from entpy.runtime.predicate import PredicateFactory


@dataclass
class Registry:
    graph: Graph
    tables: dict[str, Table]
    nodes: dict[type[Schema], NodeDescriptor]
    _predicates: dict[type[Schema], PredicateFactory]
    storage: str = "sql"
    _edge_cache: dict[tuple[type[Schema], str], ResolvedEdge | None] = field(
        default_factory=dict, repr=False
    )
    _table_schema_cache: dict[str, type[Schema] | None] = field(
        default_factory=dict, repr=False
    )

    @classmethod
    def from_schemas(cls, schemas: list[type[Schema]], *, storage: str = "sql") -> Registry:
        if storage not in ("sql", "gremlin"):
            raise ValueError(f"unknown storage {storage!r}")
        graph = build_graph(schemas)
        tables = {} if storage == "gremlin" else tables_for_graph(graph)
        nodes = {n.schema_type: n for n in graph.nodes.values()}
        preds = {}
        for st, node in nodes.items():
            field_map = {f.name: f.column for f in node.fields}
            field_map["id"] = "id"
            preds[st] = PredicateFactory(st, field_map)
        return cls(graph=graph, tables=tables, nodes=nodes, _predicates=preds, storage=storage)

    def node_for(self, schema: type[Schema]) -> NodeDescriptor:
        return self.nodes[schema]

    def label_for(self, schema: type[Schema]) -> str:
        return self.node_for(schema).resolved_table()

    def table_for(self, schema: type[Schema]) -> Table:
        node = self.node_for(schema)
        if self.storage == "gremlin":
            raise RuntimeError("table_for unavailable for gremlin storage; use label_for")
        return self.tables[node.resolved_table()]

    def F(self, schema: type[Schema]) -> PredicateFactory:
        return self._predicates[schema]

    def edges_for(self, schema: type[Schema]) -> list[ResolvedEdge]:
        node = self.node_for(schema)
        return [e for e in self.graph.edges if e.owner.name == node.name]

    def resolve_edge(self, schema: type[Schema], edge_name: str) -> ResolvedEdge | None:
        key = (schema, edge_name)
        if key in self._edge_cache:
            return self._edge_cache[key]
        for e in self.edges_for(schema):
            if e.name == edge_name:
                self._edge_cache[key] = e
                return e
        self._edge_cache[key] = None
        return None

    def schema_for_table(self, table_name: str) -> type[Schema] | None:
        if table_name in self._table_schema_cache:
            return self._table_schema_cache[table_name]
        for st, node in self.nodes.items():
            if node.resolved_table() == table_name:
                self._table_schema_cache[table_name] = st
                return st
        self._table_schema_cache[table_name] = None
        return None
