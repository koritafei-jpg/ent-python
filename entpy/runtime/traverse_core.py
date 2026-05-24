"""TraverseChain / AsyncTraverseChain 共享逻辑（减少 sync/async 重复）。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from entpy.ir.graph import ResolvedEdge
from entpy.runtime.entity import Entity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.predicate import Predicate
from entpy.schema.base import Schema


def resolve_hops(
    client: Any,
    entity: Entity,
    hops: list[str],
    cache: list[ResolvedEdge] | None,
) -> tuple[list[ResolvedEdge], list[ResolvedEdge]]:
    if cache is not None:
        return cache, cache
    if not hops:
        raise ValueError("traverse 需要至少一条边，请使用 .out('edge_name')")
    resolved: list[ResolvedEdge] = []
    schema: type[Schema] = entity._schema
    for name in hops:
        re = client._registry.resolve_edge(schema, name)
        if re is None:
            raise ValueError(f"unknown edge {name!r} on {schema.type_name()}")
        resolved.append(re)
        schema = re.peer.schema_type
    return resolved, resolved


def branch_chain(
    chain_cls: type,
    client: Any,
    entity: Entity,
    hops: list[str],
    predicates: list[Predicate],
    limit: int | None,
    project_field: str | None,
    resolved_cache: list[ResolvedEdge] | None,
) -> Any:
    chain = chain_cls(client, entity, list(hops))
    chain._predicates = list(predicates)
    chain._limit = limit
    chain._project_field = project_field
    if resolved_cache is not None and hops:
        chain._resolved_hops_cache = resolved_cache
    return chain


def walk_multi_hop(
    entity: Entity,
    hops: list[str],
    hop_batch: Callable[[Any, list[Entity], str], list[Entity]],
    client: Any,
) -> list[Entity]:
    current: list[Entity] = [entity]
    for edge_name in hops:
        next_entities: list[Entity] = []
        seen: set[Any] = set()
        for neighbor in hop_batch(client, current, edge_name):
            if neighbor.id in seen:
                continue
            seen.add(neighbor.id)
            next_entities.append(neighbor)
        current = next_entities
    return current


async def walk_multi_hop_async(
    entity: Entity,
    hops: list[str],
    hop_batch: Callable[[list[Entity], str], Awaitable[list[Entity]]],
) -> list[Entity]:
    """多跳慢路径（async）：与 ``walk_multi_hop`` 语义一致。"""
    current: list[Entity] = [entity]
    for edge_name in hops:
        next_entities: list[Entity] = []
        seen: set[Any] = set()
        for neighbor in await hop_batch(current, edge_name):
            if neighbor.id in seen:
                continue
            seen.add(neighbor.id)
            next_entities.append(neighbor)
        current = next_entities
    return current


def traverse_only(rows: list[Any], project_field: str | None) -> Entity:
    if not rows:
        raise NotFoundError("traverse: not found")
    if len(rows) > 1:
        raise NotFoundError("traverse: not unique")
    if project_field:
        raise TypeError("values() 投影模式下不能使用 only()")
    return rows[0]


def traverse_ids(rows: list[Any], project_field: str | None) -> list[Any]:
    if project_field:
        raise TypeError("values() 投影模式下不能使用 ids()")
    return [e.id for e in rows]
