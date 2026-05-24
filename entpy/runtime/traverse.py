"""从实体出发的边遍历（支持多跳链式 .out()）。"""

from __future__ import annotations

from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph_async
from entpy.dialect.sqlalchemy.sqlgraph import load_neighbors_sql, load_neighbors_sql_batch
from entpy.ir.graph import ResolvedEdge
from entpy.runtime.entity import Entity
from entpy.runtime.predicate import Predicate
from entpy.runtime import traverse_core as tc
from entpy.runtime.traverse_exec import TraverseState, run_all_async, run_all_sync
from entpy.schema.base import Schema


def _hop_neighbors(client: Any, entity: Entity, edge_name: str) -> list[Entity]:
    re = client._registry.resolve_edge(entity._schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

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

        tables = client._registry.tables
        owner_table = client._registry.label_for(entity._schema)
        rows = load_neighbors_sql(
            session,
            tables,
            owner_id=entity.id,
            owner_data=entity._data,
            owner_table=owner_table,
            re=re,
        )
        return [Entity(peer_schema, r, client) for r in rows]


def _assert_same_schema(entities: list[Entity]) -> type[Schema]:
    schema = entities[0]._schema
    for entity in entities[1:]:
        if entity._schema is not schema:
            raise ValueError(
                "batch neighbor load requires entities of the same schema"
            )
    return schema


def _hop_neighbors_batch(
    client: Any, entities: list[Entity], edge_name: str
) -> list[Entity]:
    if not entities:
        return []
    schema = _assert_same_schema(entities)
    re = client._registry.resolve_edge(schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

    if len(entities) == 1:
        return _hop_neighbors(client, entities[0], edge_name)

    if client._driver.dialect() == "gremlin":
        from entpy.dialect.gremlin import graph_ops

        owner_ids = [e.id for e in entities]
        grouped = graph_ops.load_edge_neighbors_batch(
            client._driver.g, client._registry, owner_ids, re
        )
        out: list[Entity] = []
        seen: set[Any] = set()
        for entity in entities:
            for row in grouped.get(entity.id, []):
                rid = row.get("id")
                if rid in seen:
                    continue
                seen.add(rid)
                out.append(Entity(peer_schema, row, client))
        return out

    owner_ids = [e.id for e in entities]
    owner_rows = {e.id: e._data for e in entities}
    owner_table = client._registry.label_for(schema)
    tables = client._registry.tables
    out: list[Entity] = []
    with client._driver.session() as session:
        grouped = load_neighbors_sql_batch(
            session,
            tables,
            owner_ids=owner_ids,
            owner_rows=owner_rows,
            owner_table=owner_table,
            re=re,
        )
        for rows in grouped.values():
            out.extend(Entity(peer_schema, r, client) for r in rows)
    return out


async def _hop_neighbors_async(client: Any, entity: Entity, edge_name: str) -> list[Entity]:
    re = client._registry.resolve_edge(entity._schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

    if client._driver.dialect() == "gremlin":
        from entpy.dialect.gremlin import graph_ops

        rows = await client._driver.run(
            lambda: graph_ops.traverse_neighbors(
                client._driver.g,
                client._registry,
                owner_label=client._registry.label_for(entity._schema),
                owner_id=entity.id,
                edge=re,
            )
        )
        return [Entity(peer_schema, r, client) for r in rows]

    tables = client._registry.tables
    owner_table = client._registry.label_for(entity._schema)
    async with client._driver.session() as session:
        rows = await sqlgraph_async.load_neighbors_sql(
            session,
            tables,
            owner_id=entity.id,
            owner_data=entity._data,
            owner_table=owner_table,
            re=re,
        )
    return [Entity(peer_schema, r, client) for r in rows]


async def _hop_neighbors_batch_async(
    client: Any, entities: list[Entity], edge_name: str
) -> list[Entity]:
    if not entities:
        return []
    schema = _assert_same_schema(entities)
    re = client._registry.resolve_edge(schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

    if len(entities) == 1:
        return await _hop_neighbors_async(client, entities[0], edge_name)

    if client._driver.dialect() == "gremlin":
        from entpy.dialect.gremlin import graph_ops

        owner_ids = [e.id for e in entities]

        def _run():
            return graph_ops.load_edge_neighbors_batch(
                client._driver.g, client._registry, owner_ids, re
            )

        grouped = await client._driver.run(_run)
        out: list[Entity] = []
        seen: set[Any] = set()
        for entity in entities:
            for row in grouped.get(entity.id, []):
                rid = row.get("id")
                if rid in seen:
                    continue
                seen.add(rid)
                out.append(Entity(peer_schema, row, client))
        return out

    owner_ids = [e.id for e in entities]
    owner_rows = {e.id: e._data for e in entities}
    owner_table = client._registry.label_for(schema)
    tables = client._registry.tables
    out: list[Entity] = []
    async with client._driver.session() as session:
        grouped = await sqlgraph_async.load_neighbors_sql_batch(
            session,
            tables,
            owner_ids=owner_ids,
            owner_rows=owner_rows,
            owner_table=owner_table,
            re=re,
        )
        for rows in grouped.values():
            out.extend(Entity(peer_schema, r, client) for r in rows)
    return out


class _TraverseChainBase:
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
        self._resolved_hops_cache: list[ResolvedEdge] | None = None

    def _resolve_hops(self) -> list[ResolvedEdge]:
        resolved, cache = tc.resolve_hops(
            self._client,
            self._entity,
            self._hops,
            self._resolved_hops_cache,
        )
        self._resolved_hops_cache = cache
        return resolved

    def _peer_schema(self) -> type[Schema]:
        return self._resolve_hops()[-1].peer.schema_type

    def _branch(self) -> Any:
        return tc.branch_chain(
            self.__class__,
            self._client,
            self._entity,
            self._hops,
            self._predicates,
            self._limit,
            self._project_field,
            self._resolved_hops_cache,
        )

    def _state(self) -> TraverseState:
        return TraverseState(
            client=self._client,
            entity=self._entity,
            hops=self._hops,
            predicates=self._predicates,
            limit=self._limit,
            project_field=self._project_field,
            resolved_cache=self._resolved_hops_cache,
        )


class TraverseChain(_TraverseChainBase):
    def out(self, edge_name: str) -> TraverseChain:
        chain = TraverseChain(self._client, self._entity, self._hops + [edge_name])
        chain._predicates = list(self._predicates)
        chain._limit = self._limit
        chain._project_field = self._project_field
        chain._resolved_hops_cache = None
        return chain

    def where(self, *preds: Predicate) -> TraverseChain:
        chain = self._branch()
        chain._predicates.extend(preds)
        return chain

    def limit(self, n: int) -> TraverseChain:
        chain = self._branch()
        chain._limit = n
        return chain

    def values(self, field: str) -> TraverseChain:
        chain = self._branch()
        chain._project_field = field
        return chain

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

    def all(self) -> list[Any]:
        state = self._state()
        return run_all_sync(
            state,
            hop_single=lambda: _hop_neighbors(
                self._client, self._entity, self._hops[0]
            ),
            hop_batch=_hop_neighbors_batch,
            filter_entities=self._filter_entities,
        )

    def only(self) -> Entity:
        chain = self._branch()
        chain._limit = 2
        return tc.traverse_only(chain.all(), self._project_field)

    def ids(self) -> list[Any]:
        return tc.traverse_ids(self.all(), self._project_field)


class AsyncTraverseChain(_TraverseChainBase):
    def out(self, edge_name: str) -> AsyncTraverseChain:
        chain = AsyncTraverseChain(
            self._client, self._entity, self._hops + [edge_name]
        )
        chain._predicates = list(self._predicates)
        chain._limit = self._limit
        chain._project_field = self._project_field
        chain._resolved_hops_cache = None
        return chain

    def where(self, *preds: Predicate) -> AsyncTraverseChain:
        chain = self._branch()
        chain._predicates.extend(preds)
        return chain

    def limit(self, n: int) -> AsyncTraverseChain:
        chain = self._branch()
        chain._limit = n
        return chain

    def values(self, field: str) -> AsyncTraverseChain:
        chain = self._branch()
        chain._project_field = field
        return chain

    async def _filter_entities(
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
        return await qb.all()

    async def all(self) -> list[Any]:
        state = self._state()

        async def hop_single():
            return await _hop_neighbors_async(
                self._client, self._entity, self._hops[0]
            )

        async def hop_batch(current: list[Entity], edge_name: str):
            return await _hop_neighbors_batch_async(
                self._client, current, edge_name
            )

        return await run_all_async(
            state,
            hop_single=hop_single,
            hop_batch=hop_batch,
            filter_entities=self._filter_entities,
        )

    async def only(self) -> Entity:
        chain = self._branch()
        chain._limit = 2
        return tc.traverse_only(await chain.all(), self._project_field)

    async def ids(self) -> list[Any]:
        return tc.traverse_ids(await self.all(), self._project_field)


TraverseQuery = TraverseChain
