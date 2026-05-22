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
)

import json

from entpy.schema.field import FieldType
from entpy.ir.graph import Graph
from entpy.schema.edge import RelType
from entpy.dialect.sqlalchemy.pgvector import VectorType


def build_metadata(graph: Graph) -> tuple[MetaData, dict[str, Table]]:
    meta = MetaData()
    table_names = {n: node.resolved_table() for n, node in graph.nodes.items()}
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
        cols = [Column("id", Integer, primary_key=True, autoincrement=True)]
        for f in node.fields:
            cols.append(_column_for_field(f))
        for tbl, fk_col, ref_tbl in fk_pending:
            if tbl == tname and fk_col not in [c.name for c in cols]:
                cols.append(Column(fk_col, Integer, nullable=True))
        tables[tname] = Table(tname, meta, *cols)

    # 多对多连接表
    for jt, (c1, c2) in graph.join_tables.items():
        g, u = graph.nodes.get("Group"), graph.nodes.get("User")
        if g and u:
            tables[jt] = Table(
                jt,
                meta,
                Column(c1, Integer, ForeignKey(tables[g.resolved_table()].c.id), primary_key=True),
                Column(c2, Integer, ForeignKey(tables[u.resolved_table()].c.id), primary_key=True),
            )

    return meta, tables


def _column_for_field(f) -> Column:
    if f.typ == FieldType.VECTOR:
        dim = f.vector_dimensions or 1536
        return Column(f.column, VectorType(dim), nullable=f.optional)
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
