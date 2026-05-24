"""将 EntQL 风格 JSON 过滤器转换为 Predicate 列表。"""

from __future__ import annotations

from typing import Any

from entpy.runtime.predicate import Predicate, PredicateFactory


def _unsatisfiable_predicate() -> Predicate:
    """空 ``or`` / 恒假条件（SQL ``false()``；Gremlin ``where(constant(false))``）。"""
    from sqlalchemy import false as sql_false

    def fn(t):
        return sql_false()

    def gremlin_fn(t):
        from gremlinpython.process.graph_traversal import __

        return t.where(__.constant(False))

    return Predicate(fn, gremlin_fn)


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
            if not isinstance(value, list):
                raise ValueError("entql 'and' must be a list of filters")
            for sub in value:
                preds.extend(entql_to_predicates(F, sub))
            continue
        if key == "or":
            if not isinstance(value, list):
                raise ValueError("entql 'or' must be a list of filters")
            from sqlalchemy import or_

            parts: list[Predicate] = []
            for sub in value:
                parts.extend(entql_to_predicates(F, sub))
            if not parts:
                preds.append(_unsatisfiable_predicate())
                continue

            def combined(t):
                return or_(*[p.apply(t) for p in parts])

            def combined_gremlin(t):
                from gremlinpython.process.traversal import __

                branches = []
                for p in parts:
                    if p._gremlin_fn is None:
                        raise RuntimeError(
                            "entql or(): predicate has no gremlin implementation"
                        )
                    branches.append(p.apply_gremlin(__))
                return t.or_(*branches)

            preds.append(Predicate(combined, combined_gremlin))
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
