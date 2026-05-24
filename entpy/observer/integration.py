"""Client 启动时收集 Observer 并并入 Hook 链。"""

from __future__ import annotations

from entpy.observer.discovery import discover_observers
from entpy.observer.hooks import observers_to_hooks
from entpy.observer.base import Observer
from entpy.runtime.hook import Hook
from entpy.schema.base import Schema


def setup_observers(
    schemas: list[type[Schema]],
    *,
    observer_packages: list[str] | None = None,
    extra_hooks: list[Hook] | None = None,
) -> tuple[list[Hook], list[Observer]]:
    observers = discover_observers(schemas, observer_packages=observer_packages)
    hooks = list(extra_hooks or []) + observers_to_hooks(observers)
    return hooks, observers
