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
        owner_tbl = tables[owner_table]
        fk_map: dict[Any, Any] = {}
        stmt = select(owner_tbl.c.id, getattr(owner_tbl.c, fk)).where(
            owner_tbl.c.id.in_(owner_ids)
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
    if edge.rel in (RelType.O2M, RelType.O2O) and edge.fk_columns:
        peer = tables[edge.peer_table]
        fk = edge.fk_columns[0]
        session.execute(
            update(peer).where(peer.c.id.in_(edge.ids)).values({fk: src_id})
        )


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
        _apply_edge_on_create(session, tables, spec.id, edge)
    return row


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
    return len(edges) >= 2 and all(e.join_table or e.fk_columns for e in edges)


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
