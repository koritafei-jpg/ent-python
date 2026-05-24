"""Builder 共用字段校验。"""

from __future__ import annotations

from typing import Any

from entpy.schema.base import Schema, SearchMixin


def snapshot_edges(edges: dict[str, list[Any]]) -> dict[str, list[Any]]:
    """深拷贝边 ID 列表，避免 Mutation 与 Builder 共享引用。"""
    return {name: list(ids) for name, ids in edges.items()}


def reject_immutable_updates(
    registry: Any, schema: type[Schema], fields: dict[str, Any]
) -> None:
    for f in registry.node_for(schema).fields:
        if f.immutable and f.name in fields:
            raise ValueError(f"field {f.name!r} is immutable and cannot be updated")


def collect_update_fields_after_hooks(
    schema: type[Schema],
    mutation: Any,
    explicit_fields: set[str],
) -> dict[str, Any]:
    """Update 落库字段：用户 ``set()`` 的列 + Hook 写入的检索向量等派生列。"""
    out = {
        name: mutation.fields[name]
        for name in explicit_fields
        if name in mutation.fields
    }
    if issubclass(schema, SearchMixin):
        cfg = schema.search_config()
        if cfg and cfg.vector_field and cfg.vector_field in mutation.fields:
            out[cfg.vector_field] = mutation.fields[cfg.vector_field]
    return out


def merge_mutation_into_builder(
    mutation: Any,
    *,
    fields: dict,
    edges: dict,
    allowed_field_keys: set[str] | None = None,
) -> None:
    """将 Hook 链修改后的 mutation 合并回 Builder 状态。"""
    to_merge = mutation.fields
    if allowed_field_keys is not None:
        to_merge = {k: v for k, v in mutation.fields.items() if k in allowed_field_keys}
    fields.update(to_merge)
    for name, ids in mutation.edges.items():
        if not ids:
            continue
        merged = list(edges.get(name) or [])
        for peer_id in ids:
            if peer_id not in merged:
                merged.append(peer_id)
        edges[name] = merged
