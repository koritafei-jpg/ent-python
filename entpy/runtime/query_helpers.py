"""QueryBuilder 共享辅助（同步 / 异步共用，减少重复）。"""

from __future__ import annotations

from typing import Any, Callable

from entpy.active.context import get_effective_ctx
from entpy.privacy.policy import eval_query
from entpy.runtime.entity import Entity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.interceptor import QueryRequest
from entpy.schema.base import Schema


def make_limited_request(
    schema: type[Schema],
    limit: int,
    with_edges: list[str],
    predicates: list | None = None,
) -> QueryRequest:
    return QueryRequest(
        schema=schema,
        predicates=list(predicates or []),
        limit=limit,
        with_edges=list(with_edges),
    )


def eval_and_fetch_entities(
    client: Any,
    schema: type[Schema],
    policies: list[Any],
    predicates: list[Any],
    *,
    builder_limit: int | None,
    with_edges: list[str],
    request: QueryRequest,
    fetch_rows: Callable[[QueryRequest], list[dict]],
) -> list[Entity]:
    eval_query(get_effective_ctx(client), policies, request)
    rows = fetch_rows(request)
    return [Entity(schema, r, client) for r in rows]


def entity_only(rows: list[Entity], type_name: str) -> Entity:
    if not rows:
        raise NotFoundError(f"{type_name}: not found")
    if len(rows) > 1:
        raise NotFoundError(f"{type_name}: not unique")
    return rows[0]


def entity_first(rows: list[Entity]) -> Entity | None:
    return rows[0] if rows else None
