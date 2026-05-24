"""基于 SQL 表的图操作。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from sqlalchemy import distinct, insert, select, update, delete
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import Select

from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, EdgeSpec, QuerySpec, UpdateSpec
from entpy.schema.edge import RelType

if TYPE_CHECKING:
    from entpy.ir.graph import ResolvedEdge
    from entpy.runtime.registry import Registry


def load_neighbors_sql(
    session: Session,
    tables: dict,
    *,
    owner_id: Any,
    owner_data: dict[str, Any],
    owner_table: str,
    re: ResolvedEdge,
) -> list[dict[str, Any]]:
    """按 ResolvedEdge 从 SQL 加载一跳邻居行。"""
    peer_table = tables[re.peer.resolved_table()]

    if re.join_table:
        jt = tables[re.join_table]
        peer_col, owner_col = re.join_columns
        stmt = (
            select(peer_table)
            .select_from(
                peer_table.join(jt, peer_table.c.id == getattr(jt.c, peer_col))
            )
            .where(getattr(jt.c, owner_col) == owner_id)
        )
        return [dict(r) for r in session.execute(stmt).mappings().all()]

    if not re.fk_columns:
        return []

    fk = re.fk_columns[0]
    if re.inverse:
        # 逆 FK 始终查库，避免用过期 owner_data（遍历语义以持久化为准）
        owner_tbl = tables[owner_table]
        fk_val = session.execute(
            select(getattr(owner_tbl.c, fk)).where(owner_tbl.c.id == owner_id)
        ).scalar_one_or_none()
        if fk_val is None:
            return []
        stmt = select(peer_table).where(peer_table.c.id == fk_val)
    else:
        stmt = select(peer_table).where(getattr(peer_table.c, fk) == owner_id)
    return [dict(r) for r in session.execute(stmt).mappings().all()]


def load_neighbors_sql_batch(
    session: Session,
    tables: dict,
    *,
    owner_ids: list[Any],
    owner_rows: dict[Any, dict[str, Any]],
    owner_table: str,
    re: ResolvedEdge,
) -> dict[Any, list[dict[str, Any]]]:
    """批量加载多 owner 的一跳邻居（按 owner_id 分组）。"""
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
        for row in session.execute(stmt).mappings().all():
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
            for rid, fkv in session.execute(stmt).all():
                if fkv is not None:
                    fk_map[rid] = fkv
        peer_ids = [v for v in fk_map.values() if v is not None]
        if not peer_ids:
            return out
        stmt = select(peer_table).where(peer_table.c.id.in_(peer_ids))
        peers = {r["id"]: dict(r) for r in session.execute(stmt).mappings().all()}
        for oid, fkv in fk_map.items():
            if fkv in peers:
                out[oid].append(peers[fkv])
        return out

    fk_attr = getattr(peer_table.c, fk)
    stmt = select(peer_table).where(fk_attr.in_(owner_ids))
    for row in session.execute(stmt).mappings().all():
        d = dict(row)
        out.setdefault(d[fk], []).append(d)
    return out


def create_node(session: Session, tables: dict, spec: CreateSpec) -> Any:
    table = tables[spec.table]
    stmt = insert(table).values(**spec.fields)
    if session.bind.dialect.name == "sqlite":
        result = session.execute(stmt)
        row_id = result.inserted_primary_key[0]
    else:
        result = session.execute(stmt.returning(table.c.id))
        row_id = result.scalar_one()
    for edge in spec.edges:
        _apply_edge_on_create(session, tables, row_id, edge)
    return row_id


def _insert_m2m_row(session: Session, jt, values: dict[str, Any]) -> None:
    dialect = session.bind.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

        session.execute(dialect_insert(jt).values(values).on_conflict_do_nothing())
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

        session.execute(dialect_insert(jt).values(values).on_conflict_do_nothing())
    else:
        session.execute(insert(jt).values(values))


def _apply_edge_on_create(session: Session, tables: dict, src_id: Any, edge: EdgeSpec) -> None:
    if not edge.ids:
        return
    if edge.rel == RelType.M2M and edge.join_table:
        jt = tables[edge.join_table]
        peer_col, owner_col = edge.join_columns
        for tid in edge.ids:
            _insert_m2m_row(
                session, jt, {owner_col: src_id, peer_col: tid}
            )
        return
    if edge.rel == RelType.O2O and edge.fk_columns:
        _apply_edge_o2o_fk(session, tables, src_id, edge)
        return
    if edge.rel in (RelType.O2M, RelType.M2O) and edge.fk_columns:
        peer = tables[edge.peer_table]
        fk = edge.fk_columns[0]
        session.execute(
            update(peer).where(peer.c.id.in_(edge.ids)).values({fk: src_id})
        )


def _apply_edge_o2o_fk(
    session: Session, tables: dict, src_id: Any, edge: EdgeSpec
) -> None:
    """O2O：先解除原独占关联，再绑定新 peer（避免多个 peer 同时指向同一 owner）。"""
    peer = tables[edge.peer_table]
    fk = edge.fk_columns[0]
    fk_attr = getattr(peer.c, fk)
    clear = update(peer).where(fk_attr == src_id)
    if edge.ids:
        clear = clear.where(~peer.c.id.in_(edge.ids))
    session.execute(clear.values({fk: None}))
    if edge.ids:
        session.execute(
            update(peer).where(peer.c.id.in_(edge.ids)).values({fk: src_id})
        )


def _apply_edges_on_update(
    session: Session, tables: dict, src_id: Any, edge: EdgeSpec
) -> None:
    """Update 时同步边；M2M/O2M 保持追加语义，O2O 使用独占替换。"""
    if edge.rel == RelType.O2O and edge.fk_columns:
        _apply_edge_o2o_fk(session, tables, src_id, edge)
    else:
        _apply_edge_on_create(session, tables, src_id, edge)


def update_node(session: Session, tables: dict, spec: UpdateSpec) -> dict[str, Any] | None:
    """更新节点并返回最新行；不存在时返回 ``None``。"""
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
            mapped = session.execute(stmt).mappings().one_or_none()
            if mapped is not None:
                row = dict(mapped)
        except (AttributeError, NotImplementedError):
            session.execute(
                update(table).where(table.c.id == spec.id).values(**spec.fields)
            )
    if row is None:
        mapped = (
            session.execute(select(table).where(table.c.id == spec.id))
            .mappings()
            .one_or_none()
        )
        if mapped is None:
            return None
        row = dict(mapped)
    for edge in spec.edges:
        _apply_edges_on_update(session, tables, spec.id, edge)
    return row


def edge_joinable_sql(edge: ResolvedEdge) -> bool:
    """该边是否可编译为 SQL JOIN（与 ``_join_out_step`` / ``load_neighbors_sql`` 一致）。"""
    if edge.join_table:
        return bool(edge.join_columns)
    if edge.rel == RelType.M2M:
        return False
    return bool(edge.fk_columns)


def _join_out_step(from_clause, left_tbl, peer_tbl, edge: ResolvedEdge, tables: dict):
    """将一跳 ``out`` 遍历编译为 SQL JOIN（``peer_tbl`` 应为 aliased 表）。"""
    if edge.join_table:
        jt = tables[edge.join_table]
        peer_col, owner_col = edge.join_columns
        from_clause = from_clause.join(
            jt, getattr(jt.c, owner_col) == left_tbl.c.id
        )
        from_clause = from_clause.join(
            peer_tbl, peer_tbl.c.id == getattr(jt.c, peer_col)
        )
        return from_clause, peer_tbl
    if not edge.fk_columns:
        raise ValueError(f"edge {edge.name!r} cannot be compiled to SQL JOIN")
    fk = edge.fk_columns[0]
    if edge.inverse:
        from_clause = from_clause.join(
            peer_tbl, peer_tbl.c.id == getattr(left_tbl.c, fk)
        )
    else:
        from_clause = from_clause.join(
            peer_tbl, getattr(peer_tbl.c, fk) == left_tbl.c.id
        )
    return from_clause, peer_tbl


def can_traverse_chain_sql(edges: list[ResolvedEdge]) -> bool:
    """≥2 跳且每一跳均可 JOIN；否则 ``TraverseChain`` 回退 Python 逐跳。"""
    return len(edges) >= 2 and all(edge_joinable_sql(e) for e in edges)


def traverse_chain_sql(
    session: Session,
    tables: dict,
    *,
    owner_id: Any,
    owner_table: str,
    edges: list[ResolvedEdge],
    field: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]] | list[Any]:
    """SQL 多跳 ``out`` 链：单次 JOIN 查询（≥2 跳）。"""
    if not can_traverse_chain_sql(edges):
        raise ValueError("edges cannot be compiled to SQL traverse chain")

    owner_base = tables[owner_table]
    root = aliased(owner_base, name="t0")
    from_clause = root
    left_tbl = root
    for i, edge in enumerate(edges, start=1):
        peer_base = tables[edge.peer.resolved_table()]
        peer = aliased(peer_base, name=f"t{i}")
        from_clause, left_tbl = _join_out_step(from_clause, left_tbl, peer, edge, tables)

    if field is not None:
        col = getattr(left_tbl.c, field)
        stmt = (
            select(distinct(col))
            .select_from(from_clause)
            .where(root.c.id == owner_id)
        )
    else:
        stmt = (
            select(left_tbl)
            .distinct()
            .select_from(from_clause)
            .where(root.c.id == owner_id)
        )
    if limit is not None:
        stmt = stmt.limit(limit)

    if field is not None:
        return [r[0] for r in session.execute(stmt).all()]

    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for row in session.execute(stmt).mappings().all():
        d = dict(row)
        rid = d.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(d)
    return out


def fetch_rows_page(
    session: Session,
    tables: dict,
    table_name: str,
    *,
    page_size: int,
    after_id: Any | None = None,
) -> list[dict[str, Any]]:
    """按主键升序分页读取（用于 reindex 等批量任务，避免一次加载全表）。"""
    table = tables[table_name]
    stmt = select(table).order_by(table.c.id).limit(page_size)
    if after_id is not None:
        stmt = stmt.where(table.c.id > after_id)
    return [dict(r) for r in session.execute(stmt).mappings().all()]


def batch_update_fields(
    session: Session,
    tables: dict,
    table_name: str,
    updates: list[tuple[Any, dict[str, Any]]],
) -> int:
    """批量按 id 更新字段（单 session、无 Hook，供 reindex 等内部任务）。"""
    if not updates:
        return 0
    table = tables[table_name]
    count = 0
    for row_id, fields in updates:
        if not fields:
            continue
        stmt = update(table).where(table.c.id == row_id).values(**fields)
        session.execute(stmt)
        count += 1
    return count


def delete_nodes(session: Session, tables: dict, spec: DeleteSpec) -> int:
    table = tables[spec.table]
    if spec.ids:
        stmt = delete(table).where(table.c.id.in_(spec.ids))
    elif spec.predicates:
        stmt = delete(table)
        for pred in spec.predicates:
            stmt = stmt.where(pred)
    else:
        raise ValueError("DeleteSpec requires ids or predicates")
    result = session.execute(stmt)
    return result.rowcount


def query_nodes(
    session: Session,
    tables: dict,
    spec: QuerySpec,
    registry: Registry | None = None,
) -> list[dict[str, Any]]:
    table = tables[spec.table]
    stmt: Select = select(table)
    for pred in spec.predicates:
        stmt = stmt.where(pred)
    for ob in spec.order_by:
        stmt = stmt.order_by(ob)
    if spec.limit is not None:
        stmt = stmt.limit(spec.limit)
    rows = session.execute(stmt).mappings().all()
    result = [dict(r) for r in rows]
    if spec.with_edges and registry is not None:
        _load_edges_batch(
            session, tables, registry, spec.table, result, spec.with_edges
        )
    return result


def _load_edges_batch(
    session: Session,
    tables: dict,
    registry: Registry,
    owner_table: str,
    rows: list[dict],
    edge_names: list[str],
) -> None:
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
        grouped = load_neighbors_sql_batch(
            session,
            tables,
            owner_ids=owner_ids,
            owner_rows=owner_rows,
            owner_table=owner_table,
            re=re,
        )
        for row in rows:
            row["_edges"][ename] = grouped.get(row["id"], [])


def _load_edges(
    session: Session,
    tables: dict,
    registry: Registry,
    owner_table: str,
    row: dict,
    edge_names: list[str],
) -> None:
    _load_edges_batch(session, tables, registry, owner_table, [row], edge_names)
