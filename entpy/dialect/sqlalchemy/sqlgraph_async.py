"""sqlgraph 异步实现（读路径原生 await；写路径复杂逻辑仍 run_sync）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from entpy.dialect.sqlalchemy import sqlgraph
from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, QuerySpec, UpdateSpec


async def create_node(session: AsyncSession, tables: dict, spec: CreateSpec) -> Any:
    return await session.run_sync(lambda s: sqlgraph.create_node(s, tables, spec))


async def update_node(session: AsyncSession, tables: dict, spec: UpdateSpec) -> dict[str, Any] | None:
    table = tables[spec.table]
    row: dict[str, Any] | None = None
    if spec.fields:
        stmt = (
            update(table)
            .where(table.c.id == spec.id)
            .values(**spec.fields)
            .returning(table)
        )
        try:
            result = await session.execute(stmt)
            mapped = result.mappings().one_or_none()
            if mapped is not None:
                row = dict(mapped)
        except (AttributeError, NotImplementedError):
            await session.execute(
                update(table).where(table.c.id == spec.id).values(**spec.fields)
            )
    if row is None:
        result = await session.execute(select(table).where(table.c.id == spec.id))
        mapped = result.mappings().one_or_none()
        if mapped is None:
            return None
        row = dict(mapped)

    if spec.edges:

        def _apply_edges(sync_session) -> None:
            for edge in spec.edges:
                sqlgraph._apply_edges_on_update(sync_session, tables, spec.id, edge)

        await session.run_sync(_apply_edges)
    return row


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
    table = tables[spec.table]
    stmt = select(table)
    for pred in spec.predicates:
        stmt = stmt.where(pred)
    for ob in spec.order_by:
        stmt = stmt.order_by(ob)
    if spec.limit is not None:
        stmt = stmt.limit(spec.limit)
    result = await session.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    if spec.with_edges and registry is not None:

        def _edges(sync_session) -> None:
            sqlgraph._load_edges_batch(
                sync_session, tables, registry, spec.table, rows, spec.with_edges
            )

        await session.run_sync(_edges)
    return rows


async def fetch_rows_page(
    session: AsyncSession,
    tables: dict,
    table_name: str,
    *,
    page_size: int,
    after_id: Any | None = None,
) -> list[dict[str, Any]]:
    table = tables[table_name]
    stmt = select(table).order_by(table.c.id).limit(page_size)
    if after_id is not None:
        stmt = stmt.where(table.c.id > after_id)
    result = await session.execute(stmt)
    return [dict(r) for r in result.mappings().all()]


async def batch_update_fields(
    session: AsyncSession,
    tables: dict,
    table_name: str,
    updates: list[tuple[Any, dict[str, Any]]],
) -> int:
    return await session.run_sync(
        lambda s: sqlgraph.batch_update_fields(s, tables, table_name, updates)
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
