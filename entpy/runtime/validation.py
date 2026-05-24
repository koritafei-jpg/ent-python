"""Builder 共用字段校验。"""

from __future__ import annotations

import copy
from typing import Any

from entpy.schema.base import Schema, SearchMixin
from entpy.schema.field import FieldType


def json_field_names(schema: type[Schema]) -> frozenset[str]:
    names: set[str] = set()
    for f in schema.fields():
        d = getattr(f, "_d", None)
        if d is not None and d.typ == FieldType.JSON:
            names.add(d.name)
    return frozenset(names)


def isolate_field_value(schema: type[Schema], name: str, value: Any) -> Any:
    """深拷贝 JSON / dict / list，避免调用方别名修改落库数据。"""
    if name in json_field_names(schema) and isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return value


def isolate_fields(schema: type[Schema], fields: dict[str, Any]) -> dict[str, Any]:
    """批量隔离可变字段（Create/Update Builder 与 ActiveEntity 共用）。"""
    data = dict(fields)
    json_names = json_field_names(schema)
    for name in json_names:
        if name in data:
            data[name] = copy.deepcopy(data[name])
    for key, value in list(data.items()):
        if key not in json_names:
            data[key] = isolate_field_value(schema, key, value)
    return data


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
