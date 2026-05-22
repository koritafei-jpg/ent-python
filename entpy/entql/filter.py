"""将 EntQL 风格 JSON 过滤器转换为 Predicate 列表。"""

from __future__ import annotations

from typing import Any

from entpy.runtime.predicate import Predicate, PredicateFactory


def entql_to_predicates(
    F: PredicateFactory,
    filter_obj: dict[str, Any],
) -> list[Predicate]:
    """
    Simple EntQL subset:
      {"name": "a"}
      {"age": {"gt": 10}}
      {"and": [...]} / {"or": [...]}
    """
    preds: list[Predicate] = []
    for key, value in filter_obj.items():
        if key == "and":
            for sub in value:
                preds.extend(entql_to_predicates(F, sub))
            continue
        if key == "or":
            from sqlalchemy import or_

            parts = []
            for sub in value:
                for p in entql_to_predicates(F, sub):
                    parts.append(p)
            if parts:
                def combined(t):
                    return or_(*[p.apply(t) for p in parts])

                preds.append(Predicate(combined))
            continue
        ref = getattr(F, key)
        if isinstance(value, dict):
            for op, v in value.items():
                preds.append(_op(ref, op, v))
        else:
            preds.append(ref.eq(value))
    return preds


def _op(ref, op: str, value: Any) -> Predicate:
    if op in ("eq", "=="):
        return ref.eq(value)
    if op in ("ne", "!="):
        return ref.ne(value)
    if op == "gt":
        return ref.gt(value)
    if op == "in":
        return ref.in_(value)
    raise ValueError(f"unsupported entql op: {op}")
