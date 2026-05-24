"""从实体出发的边遍历（支持多跳链式 .out()）。"""

from __future__ import annotations

from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph_async
from entpy.dialect.sqlalchemy.sqlgraph import (
    can_traverse_chain_sql,
    load_neighbors_sql,
    load_neighbors_sql_batch,
    traverse_chain_sql,
)
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


def _hop_neighbors_batch(
    client: Any, entities: list[Entity], edge_name: str
) -> list[Entity]:
    """单跳批量邻居（同 schema 的一组实体）。"""
    if not entities:
        return []
    re = client._registry.resolve_edge(entities[0]._schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

    if all(entity._edges.get(edge_name) is not None for entity in entities):
        out: list[Entity] = []
        for entity in entities:
            out.extend(
                Entity(peer_schema, e, client) for e in entity._edges[edge_name]
            )
        return out

    if len(entities) == 1:
        return _hop_neighbors(client, entities[0], edge_name)

    if client._driver.dialect() == "gremlin":
        out = []
        for entity in entities:
            out.extend(_hop_neighbors(client, entity, edge_name))
        return out

    owner_ids = [e.id for e in entities]
    owner_rows = {e.id: e._data for e in entities}
    owner_table = client._registry.label_for(entities[0]._schema)
    tables = client._registry.tables
    out = []
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

    edges = entity._edges.get(edge_name)
    if edges is not None:
        return [Entity(peer_schema, e, client) for e in edges]

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
    re = client._registry.resolve_edge(entities[0]._schema, edge_name)
    if re is None:
        raise ValueError(f"unknown edge {edge_name!r}")
    peer_schema = re.peer.schema_type

    if all(entity._edges.get(edge_name) is not None for entity in entities):
        out: list[Entity] = []
        for entity in entities:
            out.extend(
                Entity(peer_schema, e, client) for e in entity._edges[edge_name]
            )
        return out

    if len(entities) == 1:
        return await _hop_neighbors_async(client, entities[0], edge_name)

    if client._driver.dialect() == "gremlin":
        out = []
        for entity in entities:
            out.extend(await _hop_neighbors_async(client, entity, edge_name))
        return out

    owner_ids = [e.id for e in entities]
    owner_rows = {e.id: e._data for e in entities}
    owner_table = client._registry.label_for(entities[0]._schema)
    tables = client._registry.tables
    out = []
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
    """TraverseChain / AsyncTraverseChain 共享状态与 hop 解析。"""

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

    def _branch(self) -> Any:
        chain = self.__class__(self._client, self._entity, list(self._hops))
        chain._predicates = list(self._predicates)
        chain._limit = self._limit
        chain._project_field = self._project_field
        return chain


class TraverseChain(_TraverseChainBase):
    """边遍历链：``alice.out('knows').out('knows').all()``（亦可用 ``traverse(alice).out(...)``）。"""

    def out(self, edge_name: str) -> TraverseChain:
        """追加一跳边遍历。"""
        chain = TraverseChain(self._client, self._entity, self._hops + [edge_name])
        chain._predicates = list(self._predicates)
        chain._limit = self._limit
        chain._project_field = self._project_field
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
        """投影字段，``all()`` 返回该字段值列表而非实体。"""
        chain = self._branch()
        chain._project_field = field
        return chain

    def _sql_fast_path(self) -> list[Any] | None:
        if self._client._driver.dialect() == "gremlin" or self._predicates:
            return None
        if len(self._hops) < 2:
            return None
        resolved = self._resolve_hops()
        if not can_traverse_chain_sql(resolved):
            return None
        peer_schema = resolved[-1].peer.schema_type
        owner_table = self._client._registry.label_for(self._entity._schema)
        tables = self._client._registry.tables
        with self._client._driver.session() as session:
            if self._project_field:
                vals = traverse_chain_sql(
                    session,
                    tables,
                    owner_id=self._entity.id,
                    owner_table=owner_table,
                    edges=resolved,
                    field=self._project_field,
                    limit=self._limit,
                )
                return vals
            rows = traverse_chain_sql(
                session,
                tables,
                owner_id=self._entity.id,
                owner_table=owner_table,
                edges=resolved,
                limit=self._limit,
            )
            return [Entity(peer_schema, r, self._client) for r in rows]

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
        fast = self._sql_fast_path()
        if fast is not None:
            if self._project_field:
                return fast
            peer_schema = self._resolve_hops()[-1].peer.schema_type
            return self._finish(fast, peer_schema)

        resolved = self._resolve_hops()
        peer_schema = resolved[-1].peer.schema_type

        if len(self._hops) == 1:
            entities = _hop_neighbors(self._client, self._entity, self._hops[0])
            return self._finish(entities, peer_schema)

        current: list[Entity] = [self._entity]
        for edge_name in self._hops:
            next_entities: list[Entity] = []
            seen: set[Any] = set()
            for neighbor in _hop_neighbors_batch(self._client, current, edge_name):
                if neighbor.id in seen:
                    continue
                seen.add(neighbor.id)
                next_entities.append(neighbor)
            current = next_entities
        return self._finish(current, peer_schema)

    def only(self) -> Entity:
        chain = self._branch()
        chain._limit = 2
        rows = chain.all()
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


class AsyncTraverseChain(_TraverseChainBase):
    """异步边遍历链：``await alice.out('knows').all()``。"""

    def out(self, edge_name: str) -> AsyncTraverseChain:
        chain = AsyncTraverseChain(self._client, self._entity, self._hops + [edge_name])
        chain._predicates = list(self._predicates)
        chain._limit = self._limit
        chain._project_field = self._project_field
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

    async def _sql_fast_path(self) -> list[Any] | None:
        if self._client._driver.dialect() == "gremlin" or self._predicates:
            return None
        if len(self._hops) < 2:
            return None
        resolved = self._resolve_hops()
        if not can_traverse_chain_sql(resolved):
            return None
        peer_schema = resolved[-1].peer.schema_type
        owner_table = self._client._registry.label_for(self._entity._schema)
        tables = self._client._registry.tables
        async with self._client._driver.session() as session:
            if self._project_field:
                return await sqlgraph_async.traverse_chain_sql(
                    session,
                    tables,
                    owner_id=self._entity.id,
                    owner_table=owner_table,
                    edges=resolved,
                    field=self._project_field,
                    limit=self._limit,
                )
            rows = await sqlgraph_async.traverse_chain_sql(
                session,
                tables,
                owner_id=self._entity.id,
                owner_table=owner_table,
                edges=resolved,
                limit=self._limit,
            )
            return [Entity(peer_schema, r, self._client) for r in rows]

    async def _gremlin_fast_path(self) -> list[Any] | None:
        if self._client._driver.dialect() != "gremlin" or self._predicates:
            return None
        if len(self._hops) < 2:
            return None
        resolved = self._resolve_hops()
        peer_schema = resolved[-1].peer.schema_type
        from entpy.dialect.gremlin import graph_ops

        owner_label = self._client._registry.label_for(self._entity._schema)

        if self._project_field:
            vals = await self._client._driver.run(
                lambda: graph_ops.traverse_chain_values(
                    self._client._driver.g,
                    self._client._registry,
                    owner_id=self._entity.id,
                    owner_label=owner_label,
                    edges=resolved,
                    field=self._project_field,
                )
            )
            if self._limit is not None:
                vals = vals[: self._limit]
            return vals

        rows = await self._client._driver.run(
            lambda: graph_ops.traverse_chain(
                self._client._driver.g,
                self._client._registry,
                owner_id=self._entity.id,
                owner_label=owner_label,
                edges=resolved,
            )
        )
        entities = [Entity(peer_schema, r, self._client) for r in rows]
        if self._limit is not None:
            entities = entities[: self._limit]
        return entities

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

    async def _finish(self, entities: list[Entity], peer_schema: type[Schema]) -> list[Any]:
        entities = await self._filter_entities(entities, peer_schema)
        if self._limit is not None and not self._predicates:
            entities = entities[: self._limit]
        if self._project_field:
            field = self._project_field
            return [e._data.get(field) for e in entities]
        return entities

    async def all(self) -> list[Any]:
        fast = await self._gremlin_fast_path()
        if fast is not None:
            return fast
        fast = await self._sql_fast_path()
        if fast is not None:
            if self._project_field:
                return fast
            peer_schema = self._resolve_hops()[-1].peer.schema_type
            return await self._finish(fast, peer_schema)

        resolved = self._resolve_hops()
        peer_schema = resolved[-1].peer.schema_type

        if len(self._hops) == 1:
            entities = await _hop_neighbors_async(
                self._client, self._entity, self._hops[0]
            )
            return await self._finish(entities, peer_schema)

        current: list[Entity] = [self._entity]
        for edge_name in self._hops:
            next_entities: list[Entity] = []
            seen: set[Any] = set()
            for neighbor in await _hop_neighbors_batch_async(
                self._client, current, edge_name
            ):
                if neighbor.id in seen:
                    continue
                seen.add(neighbor.id)
                next_entities.append(neighbor)
            current = next_entities
        return await self._finish(current, peer_schema)

    async def only(self) -> Entity:
        chain = self._branch()
        chain._limit = 2
        rows = await chain.all()
        if not rows:
            raise NotFoundError("traverse: not found")
        if len(rows) > 1:
            raise NotFoundError("traverse: not unique")
        if self._project_field:
            raise TypeError("values() 投影模式下不能使用 only()")
        return rows[0]

    async def ids(self) -> list[Any]:
        if self._project_field:
            raise TypeError("values() 投影模式下不能使用 ids()")
        return [e.id for e in await self.all()]


# 兼容旧名
TraverseQuery = TraverseChain
