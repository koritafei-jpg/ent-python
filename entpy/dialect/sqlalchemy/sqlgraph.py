"""基于 SQL 表的图操作。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert, select, update, delete, and_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, EdgeSpec, QuerySpec, UpdateSpec
from entpy.schema.edge import RelType
from entpy.runtime.errors import ConstraintError


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


def _apply_edge_on_create(session: Session, tables: dict, src_id: Any, edge: EdgeSpec) -> None:
    if not edge.ids:
        return
    if edge.rel == RelType.M2M and edge.join_table:
        jt = tables[edge.join_table]
        c1, c2 = edge.join_columns
        for tid in edge.ids:
            if edge.name == "users":
                session.execute(insert(jt).values({c1: src_id, c2: tid}))
            else:
                session.execute(insert(jt).values({c1: tid, c2: src_id}))
        return
    if edge.rel in (RelType.O2M, RelType.O2O) and edge.fk_columns:
        peer = tables[edge.peer_table]
        fk = edge.fk_columns[0]
        session.execute(
            update(peer).where(peer.c.id.in_(edge.ids)).values({fk: src_id})
        )


def update_node(session: Session, tables: dict, spec: UpdateSpec) -> None:
    table = tables[spec.table]
    if spec.fields:
        session.execute(update(table).where(table.c.id == spec.id).values(**spec.fields))
    for edge in spec.edges:
        _apply_edge_on_create(session, tables, spec.id, edge)


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


def query_nodes(session: Session, tables: dict, spec: QuerySpec) -> list[dict[str, Any]]:
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
    if spec.with_edges:
        for row in result:
            _load_edges(session, tables, spec.table, row, spec.with_edges)
    return result


def _load_edges(
    session: Session,
    tables: dict,
    owner_table: str,
    row: dict,
    edge_names: list[str],
) -> None:
    rid = row["id"]
    if owner_table == "users":
        cars = tables.get("cars")
        if cars is not None and "cars" in edge_names:
            fk = cars.c.user_cars
            rows = session.execute(select(cars).where(fk == rid)).mappings().all()
            row["_edges"] = row.get("_edges", {})
            row["_edges"]["cars"] = [dict(r) for r in rows]
        if "groups" in edge_names:
            jt = tables.get("group_users")
            groups = tables.get("groups")
            if jt is not None and groups is not None:
                stmt = (
                    select(groups)
                    .select_from(groups.join(jt, groups.c.id == jt.c.group_id))
                    .where(jt.c.user_id == rid)
                )
                rows = session.execute(stmt).mappings().all()
                row["_edges"] = row.get("_edges", {})
                row["_edges"]["groups"] = [dict(r) for r in rows]
