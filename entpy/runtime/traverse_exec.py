"""Traverse 执行协议：统一 SQL/Gremlin 快路径与 all() 流程。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from entpy.dialect.sqlalchemy import sqlgraph_async
from entpy.dialect.sqlalchemy.sqlgraph import can_traverse_chain_sql, traverse_chain_sql
from entpy.ir.graph import ResolvedEdge
from entpy.runtime import traverse_core as tc
from entpy.runtime.entity import Entity
from entpy.runtime.predicate import Predicate
from entpy.schema.base import Schema

T = TypeVar("T")


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


def _finish_after_fast(
    state: TraverseState,
    fast: list[Any],
    filter_entities: Callable[[list[Entity], type[Schema]], list[Entity]],
) -> list[Any]:
    if state.project_field:
        return fast
    return tc.finish_entities(
        fast,
        state.peer_schema(),
        client=state.client,
        predicates=state.predicates,
        limit=state.limit,
        project_field=state.project_field,
        filter_entities=filter_entities,
    )


async def _finish_after_fast_async(
    state: TraverseState,
    fast: list[Entity],
    filter_entities: Callable[
        [list[Entity], type[Schema]], Awaitable[list[Entity]]
    ],
) -> list[Any]:
    if state.project_field:
        return fast
    filtered = await filter_entities(fast, state.peer_schema())
    if state.limit is not None and not state.predicates:
        filtered = filtered[: state.limit]
    if state.project_field:
        field = state.project_field
        return [e._data.get(field) for e in filtered]
    return filtered


def run_all_sync(
    state: TraverseState,
    *,
    hop_single: Callable[[], list[Entity]],
    hop_batch: Callable[[list[Entity], str], list[Entity]],
    filter_entities: Callable[[list[Entity], type[Schema]], list[Entity]],
) -> list[Any]:
    fast = try_gremlin_fast_path_sync(state)
    if fast is not None:
        return fast
    fast = try_sql_fast_path_sync(state)
    if fast is not None:
        return _finish_after_fast(state, fast, filter_entities)

    resolved = state.resolved_hops()
    peer_schema = resolved[-1].peer.schema_type
    if len(state.hops) == 1:
        return tc.finish_entities(
            hop_single(),
            peer_schema,
            client=state.client,
            predicates=state.predicates,
            limit=state.limit,
            project_field=state.project_field,
            filter_entities=filter_entities,
        )
    current = tc.walk_multi_hop(state.entity, state.hops, hop_batch, state.client)
    return tc.finish_entities(
        current,
        peer_schema,
        client=state.client,
        predicates=state.predicates,
        limit=state.limit,
        project_field=state.project_field,
        filter_entities=filter_entities,
    )


async def run_all_async(
    state: TraverseState,
    *,
    hop_single: Callable[[], Awaitable[list[Entity]]],
    hop_batch: Callable[[list[Entity], str], Awaitable[list[Entity]]],
    filter_entities: Callable[[list[Entity], type[Schema]], Awaitable[list[Entity]]],
) -> list[Any]:
    fast = await try_gremlin_fast_path_async(state)
    if fast is not None:
        return fast
    fast = await try_sql_fast_path_async(state)
    if fast is not None:
        return await _finish_after_fast_async(state, fast, filter_entities)

    resolved = state.resolved_hops()
    peer_schema = resolved[-1].peer.schema_type
    if len(state.hops) == 1:
        entities = await hop_single()
        filtered = await filter_entities(entities, peer_schema)
        if state.limit is not None and not state.predicates:
            filtered = filtered[: state.limit]
        if state.project_field:
            return [e._data.get(state.project_field) for e in filtered]
        return filtered

    current: list[Entity] = [state.entity]
    for edge_name in state.hops:
        next_entities: list[Entity] = []
        seen: set[Any] = set()
        for neighbor in await hop_batch(current, edge_name):
            if neighbor.id in seen:
                continue
            seen.add(neighbor.id)
            next_entities.append(neighbor)
        current = next_entities

    filtered = await filter_entities(current, peer_schema)
    if state.limit is not None and not state.predicates:
        filtered = filtered[: state.limit]
    if state.project_field:
        return [e._data.get(state.project_field) for e in filtered]
    return filtered
