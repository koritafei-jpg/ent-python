"""同步 / 异步查询执行（Builder 共用，保证拦截器行为一致）。"""

from __future__ import annotations

import asyncio
from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph, sqlgraph_async
from entpy.dialect.sqlalchemy.spec import QuerySpec
from entpy.runtime.interceptor import QueryRequest, chain_interceptors
from entpy.schema.base import Schema


def _is_gremlin(client: Any) -> bool:
    return client._driver.dialect() == "gremlin"


def execute_query_sync(
    client: Any,
    schema: type[Schema],
    predicates: list[Any],
    *,
    limit: int | None,
    with_edges: list[str],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    label = client._registry.label_for(schema)

    def execute(req: QueryRequest) -> list[dict[str, Any]]:
        effective_limit = req.limit if req.limit is not None else limit
        edges = req.with_edges if req.with_edges else list(with_edges)
        with client._driver.session() as session:
            if _is_gremlin(client):
                from entpy.dialect.gremlin import graph_ops

                spec = QuerySpec(
                    table=label,
                    limit=effective_limit,
                    with_edges=edges,
                )
                return graph_ops.query_nodes(
                    session.g,
                    client._registry,
                    spec,
                    gremlin_preds=list(predicates),
                )
            table = client._registry.table_for(req.schema)
            sql_preds = [p.apply(table) for p in predicates]
            spec = QuerySpec(
                table=table.name,
                predicates=sql_preds,
                limit=effective_limit,
                with_edges=edges,
            )
            return sqlgraph.query_nodes(
                session, client._registry.tables, spec, client._registry
            )

    if client._interceptors:
        return chain_interceptors(client._interceptors, execute, request)
    return execute(request)


async def execute_query_async(
    client: Any,
    schema: type[Schema],
    predicates: list[Any],
    *,
    limit: int | None,
    with_edges: list[str],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    if client._interceptors:
        return await asyncio.to_thread(
            execute_query_sync,
            client,
            schema,
            predicates,
            limit=limit,
            with_edges=with_edges,
            request=request,
        )

    label = client._registry.label_for(schema)
    if _is_gremlin(client):
        from entpy.dialect.gremlin import graph_ops

        spec = QuerySpec(
            table=label,
            limit=limit,
            with_edges=list(with_edges),
        )
        return await client._driver.run(
            lambda: graph_ops.query_nodes(
                client._driver.g,
                client._registry,
                spec,
                gremlin_preds=list(predicates),
            )
        )

    table = client._registry.table_for(schema)
    sql_preds = [p.apply(table) for p in predicates]
    spec = QuerySpec(
        table=table.name,
        predicates=sql_preds,
        limit=limit,
        with_edges=list(with_edges),
    )
    async with client._driver.session() as session:
        return await sqlgraph_async.query_nodes(
            session, client._registry.tables, spec, client._registry
        )
