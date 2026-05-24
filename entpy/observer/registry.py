"""Observer 全局注册表（@observes 与自动发现共用）。"""

from __future__ import annotations

from entpy.observer.base import Observer
from entpy.schema.base import Schema


class ObserverRegistry:
    def __init__(self) -> None:
        self._by_schema: dict[type[Schema], type[Observer]] = {}

    def register(self, schema: type[Schema], observer_cls: type[Observer]) -> None:
        self._by_schema[schema] = observer_cls

    def get(self, schema: type[Schema]) -> type[Observer] | None:
        return self._by_schema.get(schema)

    def clear(self) -> None:
        self._by_schema.clear()


_global_registry = ObserverRegistry()


def get_observer_registry() -> ObserverRegistry:
    return _global_registry
