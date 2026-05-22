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
    dry_run: bool = False,
) -> int:
    """对可检索 Schema 的全部行按 text_fields 重算 vector_field。"""
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

    rows = client.query(schema).all()
    updated = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        texts = [_row_text(row, meta.config.text_fields) for row in chunk]
        vectors = embedder.embed_sync(texts)
        for row, vec in zip(chunk, vectors):
            if dry_run:
                updated += 1
                continue
            client.update(schema, row.id).set(vec_field, vec).save()
            updated += 1
    return updated


async def reindex_async(
    client: Any,
    schema: type[Schema],
    embedder: Embedder,
    *,
    batch_size: int = 32,
    dry_run: bool = False,
) -> int:
    """reindex_sync 的异步版本。"""
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

    rows = await client.query(schema).all()
    updated = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        texts = [_row_text(row, meta.config.text_fields) for row in chunk]
        vectors = await embedder.embed(texts)
        for row, vec in zip(chunk, vectors):
            if dry_run:
                updated += 1
                continue
            await client.update(schema, row.id).set(vec_field, vec).save()
            updated += 1
    return updated


def _row_text(row: Any, text_fields: list[str]) -> str:
    parts = []
    for name in text_fields:
        val = getattr(row, name, None)
        if val:
            parts.append(str(val))
    return " ".join(parts) if parts else ""
