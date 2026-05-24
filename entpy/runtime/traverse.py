"""从实体出发的边遍历（支持多跳链式 .out()）。"""

from __future__ import annotations

from typing import Any

from entpy.dialect.sqlalchemy.spec import QuerySpec
from entpy.dialect.sqlalchemy import sqlgraph
from entpy.ir.graph import ResolvedEdge
from entpy.runtime.entity import Entity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.predicate import Predicate
from entpy.schema.base import Schema


def _hop_neighbors(client: Any, entity: Entity, edge_name: str) -> list[Entity]:
    """单跳邻居（Gremlin 或 SQL）。"""
    re = client._registry.resolve_edge(entity._schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

    edges = entity._edges.get(edge_name)
    if edges is not None:
        return [Entity(peer_schema, e, client) for e in edges]

    with client._driver.session() as session:
        if client._driver.dialect() == "gremlin":
            from entpy.dialect.gremlin import graph_ops

            rows = graph_ops.traverse_neighbors(
                session.g,
                client._registry,
                owner_label=client._registry.label_for(entity._schema),
                owner_id=entity.id,
                edge=re,
            )
            return [Entity(peer_schema, r, client) for r in rows]

        peer_table = client._registry.table_for(peer_schema)
        preds: list[Predicate] = []
        if re.fk_columns and not re.join_table:
            fk = re.fk_columns[0]
            eid = entity.id

            def _fk_pred(t, col=fk, vid=eid):
                return getattr(t.c, col) == vid

            preds.append(Predicate(_fk_pred))
        sql_preds = [p.apply(peer_table) for p in preds]
        spec = QuerySpec(table=peer_table.name, predicates=sql_preds)
        rows = sqlgraph.query_nodes(session, client._registry.tables, spec)
    return [Entity(peer_schema, r, client) for r in rows]


class TraverseChain:
    """边遍历链：``alice.out('knows').out('knows').all()``（亦可用 ``traverse(alice).out(...)``）。"""

    def __init__(
        self,
        client: Any,
        entity: Entity,
        hops: list[str] | None = None,
    ) -> None:
        self._client = client
        self._entity = entity
        self._hops: list[str] = list(hops or [])
        self._predicates: list[Predicate] = []
        self._limit: int | None = None
        self._project_field: str | None = None

    def out(self, edge_name: str) -> TraverseChain:
        """追加一跳边遍历。"""
        chain = TraverseChain(self._client, self._entity, self._hops + [edge_name])
        chain._predicates = list(self._predicates)
        chain._limit = self._limit
        chain._project_field = self._project_field
        return chain

    def where(self, *preds: Predicate) -> TraverseChain:
        self._predicates.extend(preds)
        return self

    def limit(self, n: int) -> TraverseChain:
        self._limit = n
        return self

    def values(self, field: str) -> TraverseChain:
        """投影字段，``all()`` 返回该字段值列表而非实体。"""
        self._project_field = field
        return self

    def _resolve_hops(self) -> list[ResolvedEdge]:
        if not self._hops:
            raise ValueError("traverse 需要至少一条边，请使用 .out('edge_name')")
        resolved: list[ResolvedEdge] = []
        schema: type[Schema] = self._entity._schema
        for name in self._hops:
            re = self._client._registry.resolve_edge(schema, name)
            if re is None:
                raise ValueError(
                    f"unknown edge {name!r} on {schema.type_name()}"
                )
            resolved.append(re)
            schema = re.peer.schema_type
        return resolved

    def _peer_schema(self) -> type[Schema]:
        return self._resolve_hops()[-1].peer.schema_type

    def _gremlin_fast_path(self) -> list[Any] | None:
        if self._client._driver.dialect() != "gremlin" or self._predicates:
            return None
        if len(self._hops) < 2:
            return None
        resolved = self._resolve_hops()
        peer_schema = resolved[-1].peer.schema_type
        with self._client._driver.session() as session:
            from entpy.dialect.gremlin import graph_ops

            owner_label = self._client._registry.label_for(self._entity._schema)
            if self._project_field:
                vals = graph_ops.traverse_chain_values(
                    session.g,
                    self._client._registry,
                    owner_id=self._entity.id,
                    owner_label=owner_label,
                    edges=resolved,
                    field=self._project_field,
                )
                if self._limit is not None:
                    vals = vals[: self._limit]
                return vals
            rows = graph_ops.traverse_chain(
                session.g,
                self._client._registry,
                owner_id=self._entity.id,
                owner_label=owner_label,
                edges=resolved,
            )
            entities = [Entity(peer_schema, r, self._client) for r in rows]
            if self._limit is not None:
                entities = entities[: self._limit]
            return entities

    def _filter_entities(
        self, entities: list[Entity], peer_schema: type[Schema]
    ) -> list[Entity]:
        if not self._predicates or not entities:
            return entities
        ids = [e.id for e in entities]
        qb = self._client.query(peer_schema).where(
            self._client.F(peer_schema).id.in_(ids)
        )
        for pred in self._predicates:
            qb = qb.where(pred)
        if self._limit is not None:
            qb = qb.limit(self._limit)
        return qb.all()

    def _finish(self, entities: list[Entity], peer_schema: type[Schema]) -> list[Any]:
        entities = self._filter_entities(entities, peer_schema)
        if self._limit is not None and not self._predicates:
            entities = entities[: self._limit]
        if self._project_field:
            field = self._project_field
            return [e._data.get(field) for e in entities]
        return entities

    def all(self) -> list[Any]:
        fast = self._gremlin_fast_path()
        if fast is not None:
            return fast

        resolved = self._resolve_hops()
        peer_schema = resolved[-1].peer.schema_type

        if len(self._hops) == 1:
            entities = _hop_neighbors(self._client, self._entity, self._hops[0])
            return self._finish(entities, peer_schema)

        current: list[Entity] = [self._entity]
        for edge_name in self._hops:
            next_entities: list[Entity] = []
            for ent in current:
                next_entities.extend(_hop_neighbors(self._client, ent, edge_name))
            current = next_entities
        return self._finish(current, peer_schema)

    def only(self) -> Entity:
        rows = self.limit(2).all()
        if not rows:
            raise NotFoundError("traverse: not found")
        if len(rows) > 1:
            raise NotFoundError("traverse: not unique")
        if self._project_field:
            raise TypeError("values() 投影模式下不能使用 only()")
        return rows[0]

    def ids(self) -> list[Any]:
        """终点实体 id 列表（投影模式下不可用）。"""
        if self._project_field:
            raise TypeError("values() 投影模式下不能使用 ids()")
        return [e.id for e in self.all()]


# 兼容旧名
TraverseQuery = TraverseChain
