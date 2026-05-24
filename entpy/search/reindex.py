"""对可检索实体重新计算向量列。"""

from __future__ import annotations

from typing import Any

from entpy.schema.base import Schema, SearchMixin
from entpy.search.embedder import Embedder
from entpy.search.registry import SearchRegistry


def reindex_sync(
    client: Any,
    schema: type[Schema],
    embedder: Embedder,
    *,
    batch_size: int = 32,
    page_size: int = 500,
    dry_run: bool = False,
) -> int:
    """对可检索 Schema 分页重算 vector_field（批量写库，避免全表加载与逐行 save）。"""
    meta, vec_field, table_name = _reindex_meta(client, schema)
    tables = client._registry.tables
    updated = 0
    after_id: Any | None = None

    with client._driver.session() as session:
        from entpy.dialect.sqlalchemy import sqlgraph

        while True:
            rows = sqlgraph.fetch_rows_page(
                session, tables, table_name, page_size=page_size, after_id=after_id
            )
            if not rows:
                break
            for i in range(0, len(rows), batch_size):
                chunk = rows[i : i + batch_size]
                texts = [_row_text_dict(r, meta.config.text_fields) for r in chunk]
                vectors = embedder.embed_sync(texts)
                if not dry_run:
                    pairs = [
                        (r["id"], {vec_field: vec})
                        for r, vec in zip(chunk, vectors)
                    ]
                    sqlgraph.batch_update_fields(
                        session, tables, table_name, pairs
                    )
                updated += len(chunk)
            after_id = rows[-1]["id"]
    return updated


async def reindex_async(
    client: Any,
    schema: type[Schema],
    embedder: Embedder,
    *,
    batch_size: int = 32,
    page_size: int = 500,
    dry_run: bool = False,
) -> int:
    """reindex_sync 的异步版本。"""
    meta, vec_field, table_name = _reindex_meta(client, schema)
    tables = client._registry.tables
    updated = 0
    after_id: Any | None = None

    from entpy.dialect.sqlalchemy import sqlgraph_async

    async with client._driver.session() as session:
        while True:
            rows = await sqlgraph_async.fetch_rows_page(
                session, tables, table_name, page_size=page_size, after_id=after_id
            )
            if not rows:
                break
            for i in range(0, len(rows), batch_size):
                chunk = rows[i : i + batch_size]
                texts = [_row_text_dict(r, meta.config.text_fields) for r in chunk]
                vectors = await embedder.embed(texts)
                if not dry_run:
                    pairs = [
                        (r["id"], {vec_field: vec})
                        for r, vec in zip(chunk, vectors)
                    ]
                    await sqlgraph_async.batch_update_fields(
                        session, tables, table_name, pairs
                    )
                updated += len(chunk)
            after_id = rows[-1]["id"]
    return updated


def _reindex_meta(client: Any, schema: type[Schema]):
    if not issubclass(schema, SearchMixin):
        raise TypeError(f"{schema.type_name()} is not searchable")
    if client._registry.storage == "gremlin":
        raise RuntimeError("search reindex requires SQL storage")

    sr = SearchRegistry.from_registry(client._registry)
    if not sr.has(schema):
        raise ValueError(f"{schema.type_name()} has no search_config")
    meta = sr.get(schema)
    vec_field = meta.config.vector_field
    if not vec_field:
        raise ValueError(f"{schema.type_name()} has no vector_field in search_config")
    if not meta.text_columns:
        raise ValueError(f"{schema.type_name()} has no searchable text fields")
    table_name = client._registry.table_for(schema).name
    return meta, vec_field, table_name


def _row_text(row: Any, text_fields: list[str]) -> str:
    if isinstance(row, dict):
        return _row_text_dict(row, text_fields)
    parts = []
    for name in text_fields:
        val = getattr(row, name, None)
        if val:
            parts.append(str(val))
    return " ".join(parts) if parts else ""


def _row_text_dict(row: dict[str, Any], text_fields: list[str]) -> str:
    parts = []
    for name in text_fields:
        val = row.get(name)
        if val:
            parts.append(str(val))
    return " ".join(parts) if parts else ""
