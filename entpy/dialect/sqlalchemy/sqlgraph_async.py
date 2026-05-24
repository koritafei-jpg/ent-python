"""sqlgraph 异步封装。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from entpy.dialect.sqlalchemy import sqlgraph
from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, QuerySpec, UpdateSpec


async def create_node(session: AsyncSession, tables: dict, spec: CreateSpec) -> Any:
    return await session.run_sync(lambda s: sqlgraph.create_node(s, tables, spec))


async def update_node(session: AsyncSession, tables: dict, spec: UpdateSpec) -> dict[str, Any]:
    return await session.run_sync(lambda s: sqlgraph.update_node(s, tables, spec))


async def traverse_chain_sql(
    session: AsyncSession,
    tables: dict,
    *,
    owner_id: Any,
    owner_table: str,
    edges: list[Any],
    field: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]] | list[Any]:
    return await session.run_sync(
        lambda s: sqlgraph.traverse_chain_sql(
            s,
            tables,
            owner_id=owner_id,
            owner_table=owner_table,
            edges=edges,
            field=field,
            limit=limit,
        )
    )


async def delete_nodes(session: AsyncSession, tables: dict, spec: DeleteSpec) -> int:
    return await session.run_sync(lambda s: sqlgraph.delete_nodes(s, tables, spec))


async def query_nodes(
    session: AsyncSession, tables: dict, spec: QuerySpec, registry=None
) -> list[dict]:
    return await session.run_sync(
        lambda s: sqlgraph.query_nodes(s, tables, spec, registry)
    )


async def load_neighbors_sql(
    session: AsyncSession,
    tables: dict,
    *,
    owner_id: Any,
    owner_data: dict[str, Any],
    owner_table: str,
    re: Any,
) -> list[dict[str, Any]]:
    return await session.run_sync(
        lambda s: sqlgraph.load_neighbors_sql(
            s,
            tables,
            owner_id=owner_id,
            owner_data=owner_data,
            owner_table=owner_table,
            re=re,
        )
    )


async def load_neighbors_sql_batch(
    session: AsyncSession,
    tables: dict,
    *,
    owner_ids: list[Any],
    owner_rows: dict[Any, dict[str, Any]],
    owner_table: str,
    re: Any,
) -> dict[Any, list[dict[str, Any]]]:
    return await session.run_sync(
        lambda s: sqlgraph.load_neighbors_sql_batch(
            s,
            tables,
            owner_ids=owner_ids,
            owner_rows=owner_rows,
            owner_table=owner_table,
            re=re,
        )
    )
