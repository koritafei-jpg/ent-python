"""从 Graph 构建 SQLAlchemy MetaData。"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Uuid,
)

import json

from entpy.schema.field import FieldType
from entpy.ir.graph import Graph
from entpy.ir.descriptor import NodeDescriptor
from entpy.schema.edge import RelType
from entpy.dialect.sqlalchemy.pgvector import VectorType


def build_metadata(graph: Graph) -> tuple[MetaData, dict[str, Table]]:
    meta = MetaData()
    node_by_table = {n.resolved_table(): n for n in graph.nodes.values()}
    fk_pending: list[tuple[str, str, str]] = []  # 表名, 列名, 引用表

    for edge in graph.edges:
        if edge.rel in (RelType.O2M, RelType.M2O, RelType.O2O) and edge.fk_columns:
            if edge.inverse:
                fk_pending.append((edge.owner.resolved_table(), edge.fk_columns[0], edge.peer.resolved_table()))
            else:
                fk_pending.append((edge.peer.resolved_table(), edge.fk_columns[0], edge.owner.resolved_table()))

    tables: dict[str, Table] = {}
    for node in graph.nodes.values():
        tname = node.resolved_table()
        cols = [_pk_column(node)]
        for f in node.fields:
            if f.name == "id":
                continue
            cols.append(_column_for_field(f))
        for tbl, fk_col, ref_tbl in fk_pending:
            if tbl == tname and fk_col not in [c.name for c in cols]:
                ref_node = node_by_table.get(ref_tbl)
                cols.append(_fk_column(fk_col, ref_node))
        tables[tname] = Table(tname, meta, *cols)

    # 多对多连接表
    for jt, (c1, c2) in graph.join_tables.items():
        g, u = graph.nodes.get("Group"), graph.nodes.get("User")
        if g and u:
            tables[jt] = Table(
                jt,
                meta,
                Column(
                    c1,
                    _pk_sql_type(g),
                    ForeignKey(tables[g.resolved_table()].c.id),
                    primary_key=True,
                ),
                Column(
                    c2,
                    _pk_sql_type(u),
                    ForeignKey(tables[u.resolved_table()].c.id),
                    primary_key=True,
                ),
            )

    return meta, tables


def _id_field(node: NodeDescriptor):
    return next((f for f in node.fields if f.name == "id"), None)


def _pk_sql_type(node: NodeDescriptor):
    id_field = _id_field(node)
    if id_field and id_field.typ == FieldType.UUID:
        return Uuid(as_uuid=True)
    return Integer


def _pk_column(node: NodeDescriptor) -> Column:
    id_field = _id_field(node)
    if id_field:
        col = _column_for_field(id_field)
        col.primary_key = True
        return col
    return Column("id", Integer, primary_key=True, autoincrement=True)


def _fk_column(name: str, ref_node: NodeDescriptor | None) -> Column:
    return Column(name, _pk_sql_type(ref_node) if ref_node else Integer, nullable=True)


def _column_for_field(f) -> Column:
    if f.typ == FieldType.VECTOR:
        dim = f.vector_dimensions or 1536
        return Column(f.column, VectorType(dim), nullable=f.optional)
    if f.typ == FieldType.UUID:
        return Column(f.column, Uuid(as_uuid=True), nullable=f.optional)
    if f.typ == FieldType.INT:
        return Column(f.column, Integer, nullable=f.optional)
    if f.typ == FieldType.STRING:
        return Column(f.column, String, nullable=f.optional, default=f.default)
    if f.typ == FieldType.TIME:
        return Column(f.column, DateTime, nullable=f.optional)
    if f.typ == FieldType.FLOAT:
        return Column(f.column, Float, nullable=f.optional)
    if f.typ == FieldType.BOOL:
        return Column(f.column, Boolean, nullable=f.optional)
    if f.typ == FieldType.JSON:
        return Column(f.column, JSON, nullable=f.optional)
    return Column(f.column, String, nullable=f.optional)


def tables_for_graph(graph: Graph) -> dict[str, Table]:
    _, tables = build_metadata(graph)
    return tables
