"""用 SQL 谓词对检索结果做后过滤（BM25 / 语义 / 混合 + 条件）。"""

from __future__ import annotations

from typing import Any

from entpy.active import F, get_client
from entpy.runtime.entity import Entity
from entpy.schema.base import Schema
from entpy.search.backends.base import ScoredHit


def filter_hits(
    schema: type[Schema],
    hits: list[ScoredHit],
    **eq_fields: Any,
) -> list[ScoredHit]:
    """保留行满足全部等值条件的命中（如 category=tech, lang=en）。"""
    if not hits or not eq_fields:
        return hits
    ids = [h.id for h in hits]
    q = schema.query().where(F(schema).id.in_(ids))
    for key, value in eq_fields.items():
        q = q.where(getattr(F(schema), key).eq(value))
    allowed = {e.id for e in q.all()}
    return [h for h in hits if h.id in allowed]


def load_entities(
    schema: type[Schema],
    hits: list[ScoredHit],
    *,
    with_edges: tuple[str, ...] = (),
) -> list[Entity]:
    """按检索命中 id 加载完整实体（可选加载边）。"""
    if not hits:
        return []
    ids = [h.id for h in hits]
    q = schema.query().where(F(schema).id.in_(ids))
    if with_edges:
        q = q.with_(*with_edges)
    by_id = {e.id: e for e in q.all()}
    return [by_id[h.id] for h in hits if h.id in by_id]
