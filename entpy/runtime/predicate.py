"""谓词工厂 F(Schema)。"""

from __future__ import annotations

from typing import Any, Callable

from entpy.schema.base import Schema


def _p():
    from gremlinpython.process.traversal import P

    return P


class Predicate:
    """SQLAlchemy WHERE 片段；Gremlin 下可为遍历步骤。"""

    def __init__(
        self,
        fn: Callable[[Any], Any],
        gremlin_fn: Callable[[Any], Any] | None = None,
    ) -> None:
        self._fn = fn
        self._gremlin_fn = gremlin_fn

    def apply(self, table) -> Any:
        return self._fn(table)

    def apply_gremlin(self, traversal: Any) -> Any:
        if self._gremlin_fn is None:
            raise RuntimeError("predicate has no gremlin implementation")
        return self._gremlin_fn(traversal)


class FieldRef:
    def __init__(self, table_attr: str) -> None:
        self._attr = table_attr

    def eq(self, value: Any) -> Predicate:
        attr = self._attr

        def fn(t):
            return getattr(t.c, attr) == value

        def gremlin_fn(t):
            if attr == "id":
                return t.hasId(value)
            return t.has(attr, value)

        return Predicate(fn, gremlin_fn)

    def ne(self, value: Any) -> Predicate:
        attr = self._attr

        def fn(t):
            return getattr(t.c, attr) != value

        def gremlin_fn(t):
            return t.has(attr, _p().neq(value))

        return Predicate(fn, gremlin_fn)

    def in_(self, values: list[Any]) -> Predicate:
        attr = self._attr

        def fn(t):
            return getattr(t.c, attr).in_(values)

        def gremlin_fn(t):
            return t.has(attr, _p().within(*values))

        return Predicate(fn, gremlin_fn)

    def gt(self, value: Any) -> Predicate:
        attr = self._attr

        def fn(t):
            return getattr(t.c, attr) > value

        def gremlin_fn(t):
            return t.has(attr, _p().gt(value))

        return Predicate(fn, gremlin_fn)


class PredicateFactory:
    def __init__(self, schema: type[Schema], field_map: dict[str, str]) -> None:
        self.schema = schema
        self._fields = field_map

    def __getattr__(self, name: str) -> FieldRef:
        col = self._fields.get(name)
        if col is None and name == "id":
            col = "id"
        if col is None:
            raise AttributeError(f"unknown field {name!r} on {self.schema.type_name()}")
        return FieldRef(col)


def F(schema: type[Schema], registry: Any = None) -> PredicateFactory:
    from entpy.runtime.registry import Registry

    if registry is None:
        raise ValueError("F() requires registry; use client.F(Schema) or pass registry")
    node = registry.node_for(schema)
    field_map = {f.name: f.column for f in node.fields}
    return PredicateFactory(schema, field_map)
