"""同步 / 异步查询执行（Builder 共用，保证拦截器行为一致）。"""

from __future__ import annotations

import asyncio
from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph, sqlgraph_async
from entpy.dialect.sqlalchemy.spec import QuerySpec
from entpy.runtime.driver_util import is_gremlin_client as _is_gremlin
from entpy.runtime.interceptor import QueryRequest, chain_interceptors
from entpy.schema.base import Schema

# 同步 interceptor 桥接到 async 查询时的上限（秒），防止永久阻塞 event loop 线程
_INTERCEPTOR_BRIDGE_TIMEOUT_SEC = 300.0


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


async def _execute_query_async_impl(
    client: Any,
    schema: type[Schema],
    predicates: list[Any],
    *,
    limit: int | None,
    with_edges: list[str],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    effective_limit = request.limit if request.limit is not None else limit
    edges = request.with_edges if request.with_edges else list(with_edges)
    label = client._registry.label_for(request.schema)

    if _is_gremlin(client):
        from entpy.dialect.gremlin import graph_ops

        spec = QuerySpec(
            table=label,
            limit=effective_limit,
            with_edges=edges,
        )
        return await client._driver.run(
            lambda: graph_ops.query_nodes(
                client._driver.g,
                client._registry,
                spec,
                gremlin_preds=list(predicates),
            )
        )

    table = client._registry.table_for(request.schema)
    sql_preds = [p.apply(table) for p in predicates]
    spec = QuerySpec(
        table=table.name,
        predicates=sql_preds,
        limit=effective_limit,
        with_edges=edges,
    )
    async with client._driver.session() as session:
        return await sqlgraph_async.query_nodes(
            session, client._registry.tables, spec, client._registry
        )


async def execute_query_async(
    client: Any,
    schema: type[Schema],
    predicates: list[Any],
    *,
    limit: int | None,
    with_edges: list[str],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    if not client._interceptors:
        return await _execute_query_async_impl(
            client,
            schema,
            predicates,
            limit=limit,
            with_edges=with_edges,
            request=request,
        )

    loop = asyncio.get_running_loop()

    def run_interceptor_chain(req: QueryRequest) -> list[dict[str, Any]]:
        def terminal_execute(r: QueryRequest) -> list[dict[str, Any]]:
            future = asyncio.run_coroutine_threadsafe(
                _execute_query_async_impl(
                    client,
                    schema,
                    predicates,
                    limit=limit,
                    with_edges=with_edges,
                    request=r,
                ),
                loop,
            )
            return future.result(timeout=_INTERCEPTOR_BRIDGE_TIMEOUT_SEC)

        return chain_interceptors(client._interceptors, terminal_execute, req)

    return await asyncio.to_thread(run_interceptor_chain, request)
