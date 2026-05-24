"""Builder 共用字段校验。"""

from __future__ import annotations

from typing import Any

from entpy.schema.base import Schema


def snapshot_edges(edges: dict[str, list[Any]]) -> dict[str, list[Any]]:
    """深拷贝边 ID 列表，避免 Mutation 与 Builder 共享引用。"""
    return {name: list(ids) for name, ids in edges.items()}


def reject_immutable_updates(
    registry: Any, schema: type[Schema], fields: dict[str, Any]
) -> None:
    for f in registry.node_for(schema).fields:
        if f.immutable and f.name in fields:
            raise ValueError(f"field {f.name!r} is immutable and cannot be updated")


def merge_mutation_into_builder(mutation: Any, *, fields: dict, edges: dict) -> None:
    """将 Hook 链修改后的 mutation 合并回 Builder 状态。"""
    fields.update(mutation.fields)
    for name, ids in mutation.edges.items():
        if not ids:
            continue
        merged = list(edges.get(name) or [])
        for peer_id in ids:
            if peer_id not in merged:
                merged.append(peer_id)
        edges[name] = merged
