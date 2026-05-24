"""sqlgraph 异步实现（读路径原生 await；写路径复杂逻辑仍 run_sync）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from entpy.dialect.sqlalchemy import sqlgraph
from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, QuerySpec, UpdateSpec


async def create_node(session: AsyncSession, tables: dict, spec: CreateSpec) -> Any:
    """INSERT 原生 await；边写入复用同步 ``_apply_edge_on_create``（单次 run_sync）。"""
    table = tables[spec.table]
    stmt = insert(table).values(**spec.fields)
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "sqlite":
        result = await session.execute(stmt)
        row_id = result.inserted_primary_key[0]
    else:
        result = await session.execute(stmt.returning(table.c.id))
        row_id = result.scalar_one()
    if spec.edges:

        def _apply_edges(sync_session) -> None:
            for edge in spec.edges:
                sqlgraph._apply_edge_on_create(sync_session, tables, row_id, edge)

        await session.run_sync(_apply_edges)
    return row_id


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
    table = tables[spec.table]
    if spec.ids:
        stmt = delete(table).where(table.c.id.in_(spec.ids))
    elif spec.predicates:
        stmt = delete(table)
        for pred in spec.predicates:
            stmt = stmt.where(pred)
    else:
        raise ValueError("DeleteSpec requires ids or predicates")
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


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
        await _load_edges_batch_async(
            session, tables, registry, spec.table, rows, spec.with_edges
        )
    return rows


async def _load_edges_batch_async(
    session: AsyncSession,
    tables: dict,
    registry: Any,
    owner_table: str,
    rows: list[dict],
    edge_names: list[str],
) -> None:
    """``with_()`` 预加载：每边一次批量邻居查询（原生 await，避免 run_sync）。"""
    owner_schema = registry.schema_for_table(owner_table)
    if owner_schema is None or not rows:
        return
    owner_ids = [r["id"] for r in rows]
    owner_rows = {r["id"]: r for r in rows}
    for row in rows:
        row["_edges"] = row.get("_edges", {})
    for ename in edge_names:
        re = registry.resolve_edge(owner_schema, ename)
        if re is None:
            continue
        grouped = await load_neighbors_sql_batch(
            session,
            tables,
            owner_ids=owner_ids,
            owner_rows=owner_rows,
            owner_table=owner_table,
            re=re,
        )
        for row in rows:
            row["_edges"][ename] = grouped.get(row["id"], [])


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
    # 逆 FK 单跳与 sync 一致：始终以库中 FK 为准，不走 owner_data 缓存
    if re.fk_columns and re.inverse:
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
    grouped = await load_neighbors_sql_batch(
        session,
        tables,
        owner_ids=[owner_id],
        owner_rows={owner_id: owner_data},
        owner_table=owner_table,
        re=re,
    )
    return grouped.get(owner_id, [])


async def load_neighbors_sql_batch(
    session: AsyncSession,
    tables: dict,
    *,
    owner_ids: list[Any],
    owner_rows: dict[Any, dict[str, Any]],
    owner_table: str,
    re: Any,
) -> dict[Any, list[dict[str, Any]]]:
    """批量邻居加载（原生 await，供 query ``with_()`` / traverse 慢路径）。"""
    if not owner_ids:
        return {}
    out: dict[Any, list[dict[str, Any]]] = {oid: [] for oid in owner_ids}
    peer_table = tables[re.peer.resolved_table()]

    if re.join_table:
        jt = tables[re.join_table]
        peer_col, owner_col = re.join_columns
        owner_col_attr = getattr(jt.c, owner_col)
        stmt = (
            select(peer_table, owner_col_attr.label("_owner_id"))
            .select_from(
                peer_table.join(jt, peer_table.c.id == getattr(jt.c, peer_col))
            )
            .where(owner_col_attr.in_(owner_ids))
        )
        result = await session.execute(stmt)
        for row in result.mappings().all():
            d = dict(row)
            oid = d.pop("_owner_id")
            out.setdefault(oid, []).append(d)
        return out

    if not re.fk_columns:
        return out

    fk = re.fk_columns[0]
    if re.inverse:
        fk_map: dict[Any, Any] = {}
        missing: list[Any] = []
        for oid in owner_ids:
            row = owner_rows.get(oid) or {}
            fkv = row.get(fk)
            if fkv is not None:
                fk_map[oid] = fkv
            else:
                missing.append(oid)
        if missing:
            owner_tbl = tables[owner_table]
            stmt = select(owner_tbl.c.id, getattr(owner_tbl.c, fk)).where(
                owner_tbl.c.id.in_(missing)
            )
            result = await session.execute(stmt)
            for rid, fkv in result.all():
                if fkv is not None:
                    fk_map[rid] = fkv
        peer_ids = [v for v in fk_map.values() if v is not None]
        if not peer_ids:
            return out
        stmt = select(peer_table).where(peer_table.c.id.in_(peer_ids))
        result = await session.execute(stmt)
        peers = {r["id"]: dict(r) for r in result.mappings().all()}
        for oid, fkv in fk_map.items():
            if fkv in peers:
                out[oid].append(peers[fkv])
        return out

    fk_attr = getattr(peer_table.c, fk)
    stmt = select(peer_table).where(fk_attr.in_(owner_ids))
    result = await session.execute(stmt)
    for row in result.mappings().all():
        d = dict(row)
        out.setdefault(d[fk], []).append(d)
    return out
