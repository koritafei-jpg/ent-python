"""Traverse 执行协议：统一 SQL/Gremlin 快路径与 all() 流程。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from entpy.dialect.sqlalchemy import sqlgraph_async
from entpy.dialect.sqlalchemy.sqlgraph import can_traverse_chain_sql, traverse_chain_sql
from entpy.ir.graph import ResolvedEdge
from entpy.runtime import traverse_core as tc
from entpy.runtime.entity import Entity
from entpy.runtime.predicate import Predicate
from entpy.schema.base import Schema


@dataclass
class TraverseState:
    """TraverseChain 运行时状态（sync/async 共用）。"""

    client: Any
    entity: Entity
    hops: list[str]
    predicates: list[Predicate]
    limit: int | None
    project_field: str | None
    resolved_cache: list[ResolvedEdge] | None = None

    def resolved_hops(self) -> list[ResolvedEdge]:
        resolved, cache = tc.resolve_hops(
            self.client, self.entity, self.hops, self.resolved_cache
        )
        self.resolved_cache = cache
        return resolved

    def peer_schema(self) -> type[Schema]:
        return self.resolved_hops()[-1].peer.schema_type

    def dialect(self) -> str:
        return self.client._driver.dialect()


def _chain_fast_eligible(state: TraverseState) -> bool:
    return len(state.hops) >= 2 and not state.predicates


def _apply_limit(items: list[Any], limit: int | None) -> list[Any]:
    if limit is None:
        return items
    return items[:limit]


def _gremlin_chain_result(
    state: TraverseState,
    resolved: list[ResolvedEdge],
    g: Any,
) -> list[Any]:
    from entpy.dialect.gremlin import graph_ops

    owner_label = state.client._registry.label_for(state.entity._schema)
    registry = state.client._registry
    owner_id = state.entity.id
    if state.project_field:
        vals = graph_ops.traverse_chain_values(
            g,
            registry,
            owner_id=owner_id,
            owner_label=owner_label,
            edges=resolved,
            field=state.project_field,
        )
        return _apply_limit(vals, state.limit)
    rows = graph_ops.traverse_chain(
        g,
        registry,
        owner_id=owner_id,
        owner_label=owner_label,
        edges=resolved,
    )
    peer_schema = resolved[-1].peer.schema_type
    entities = [Entity(peer_schema, r, state.client) for r in rows]
    return _apply_limit(entities, state.limit)


def _sql_chain_result_sync(
    state: TraverseState,
    resolved: list[ResolvedEdge],
    session: Any,
    tables: dict,
) -> list[Any]:
    owner_table = state.client._registry.label_for(state.entity._schema)
    if state.project_field:
        return traverse_chain_sql(
            session,
            tables,
            owner_id=state.entity.id,
            owner_table=owner_table,
            edges=resolved,
            field=state.project_field,
            limit=state.limit,
        )
    rows = traverse_chain_sql(
        session,
        tables,
        owner_id=state.entity.id,
        owner_table=owner_table,
        edges=resolved,
        limit=state.limit,
    )
    peer_schema = resolved[-1].peer.schema_type
    return [Entity(peer_schema, r, state.client) for r in rows]


async def _sql_chain_result_async(
    state: TraverseState,
    resolved: list[ResolvedEdge],
    session: Any,
    tables: dict,
) -> list[Any]:
    owner_table = state.client._registry.label_for(state.entity._schema)
    if state.project_field:
        return await sqlgraph_async.traverse_chain_sql(
            session,
            tables,
            owner_id=state.entity.id,
            owner_table=owner_table,
            edges=resolved,
            field=state.project_field,
            limit=state.limit,
        )
    rows = await sqlgraph_async.traverse_chain_sql(
        session,
        tables,
        owner_id=state.entity.id,
        owner_table=owner_table,
        edges=resolved,
        limit=state.limit,
    )
    peer_schema = resolved[-1].peer.schema_type
    return [Entity(peer_schema, r, state.client) for r in rows]


def try_gremlin_fast_path_sync(state: TraverseState) -> list[Any] | None:
    if state.dialect() != "gremlin" or not _chain_fast_eligible(state):
        return None
    resolved = state.resolved_hops()
    with state.client._driver.session() as session:
        return _gremlin_chain_result(state, resolved, session.g)


async def try_gremlin_fast_path_async(state: TraverseState) -> list[Any] | None:
    if state.dialect() != "gremlin" or not _chain_fast_eligible(state):
        return None
    resolved = state.resolved_hops()

    def _run() -> list[Any]:
        return _gremlin_chain_result(state, resolved, state.client._driver.g)

    return await state.client._driver.run(_run)


def try_sql_fast_path_sync(state: TraverseState) -> list[Any] | None:
    if state.dialect() == "gremlin" or not _chain_fast_eligible(state):
        return None
    resolved = state.resolved_hops()
    if not can_traverse_chain_sql(resolved):
        return None
    tables = state.client._registry.tables
    try:
        with state.client._driver.session() as session:
            return _sql_chain_result_sync(state, resolved, session, tables)
    except ValueError:
        return None


async def try_sql_fast_path_async(state: TraverseState) -> list[Any] | None:
    if state.dialect() == "gremlin" or not _chain_fast_eligible(state):
        return None
    resolved = state.resolved_hops()
    if not can_traverse_chain_sql(resolved):
        return None
    tables = state.client._registry.tables
    try:
        async with state.client._driver.session() as session:
            return await _sql_chain_result_async(state, resolved, session, tables)
    except ValueError:
        return None


def _neighbor_ids_for_filter(entities: list[Entity]) -> list[Any]:
    return [e.id for e in entities]


def _filter_neighbor_query(
    state: TraverseState,
    ids: list[Any],
    peer_schema: type[Schema],
) -> Any:
    qb = state.client.query(peer_schema).where(
        state.client.F(peer_schema).id.in_(ids)
    )
    for pred in state.predicates:
        qb = qb.where(pred)
    if state.limit is not None:
        qb = qb.limit(state.limit)
    return qb


def filter_entities_sync(
    state: TraverseState,
    entities: list[Entity],
    peer_schema: type[Schema],
) -> list[Entity]:
    """慢路径 / 快路径后：按谓词二次过滤邻居。"""
    if not state.predicates or not entities:
        return entities
    ids = _neighbor_ids_for_filter(entities)
    if not ids:
        return []
    return _filter_neighbor_query(state, ids, peer_schema).all()


async def filter_entities_async(
    state: TraverseState,
    entities: list[Entity],
    peer_schema: type[Schema],
) -> list[Entity]:
    if not state.predicates or not entities:
        return entities
    ids = _neighbor_ids_for_filter(entities)
    if not ids:
        return []
    return await _filter_neighbor_query(state, ids, peer_schema).all()


def _finalize_result(state: TraverseState, entities: list[Entity]) -> list[Any]:
    if state.limit is not None and not state.predicates:
        entities = entities[: state.limit]
    if state.project_field:
        field = state.project_field
        return [e._data.get(field) for e in entities]
    return entities


def finish_sync(
    state: TraverseState,
    entities: list[Entity],
    peer_schema: type[Schema],
) -> list[Any]:
    filtered = filter_entities_sync(state, entities, peer_schema)
    return _finalize_result(state, filtered)


async def finish_async(
    state: TraverseState,
    entities: list[Entity],
    peer_schema: type[Schema],
) -> list[Any]:
    filtered = await filter_entities_async(state, entities, peer_schema)
    return _finalize_result(state, filtered)


def walk_multi_hop_slow_sync(
    state: TraverseState,
    hop_batch: Callable[[Any, list[Entity], str], list[Entity]],
) -> list[Entity]:
    """多跳慢路径（逐 hop 批量邻居）。"""
    return tc.walk_multi_hop(state.entity, state.hops, hop_batch, state.client)


async def walk_multi_hop_slow_async(
    state: TraverseState,
    hop_batch: Callable[[list[Entity], str], Awaitable[list[Entity]]],
) -> list[Entity]:
    return await tc.walk_multi_hop_async(state.entity, state.hops, hop_batch)


def _finish_fast_path(state: TraverseState, fast: list[Any]) -> list[Any]:
    if state.project_field:
        return fast
    return finish_sync(state, fast, state.peer_schema())


async def _finish_fast_path_async(state: TraverseState, fast: list[Any]) -> list[Any]:
    if state.project_field:
        return fast
    return await finish_async(state, fast, state.peer_schema())


def run_all_sync(
    state: TraverseState,
    *,
    hop_single: Callable[[], list[Entity]],
    hop_batch: Callable[[Any, list[Entity], str], list[Entity]],
) -> list[Any]:
    fast = try_gremlin_fast_path_sync(state)
    if fast is not None:
        return fast
    fast = try_sql_fast_path_sync(state)
    if fast is not None:
        return _finish_fast_path(state, fast)

    peer_schema = state.peer_schema()
    if len(state.hops) == 1:
        return finish_sync(state, hop_single(), peer_schema)
    current = walk_multi_hop_slow_sync(state, hop_batch)
    return finish_sync(state, current, peer_schema)


async def run_all_async(
    state: TraverseState,
    *,
    hop_single: Callable[[], Awaitable[list[Entity]]],
    hop_batch: Callable[[list[Entity], str], Awaitable[list[Entity]]],
) -> list[Any]:
    fast = await try_gremlin_fast_path_async(state)
    if fast is not None:
        return fast
    fast = await try_sql_fast_path_async(state)
    if fast is not None:
        return await _finish_fast_path_async(state, fast)

    peer_schema = state.peer_schema()
    if len(state.hops) == 1:
        return await finish_async(state, await hop_single(), peer_schema)
    current = await walk_multi_hop_slow_async(state, hop_batch)
    return await finish_async(state, current, peer_schema)
