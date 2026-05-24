"""按包扫描 + 命名约定自动发现 Observer。"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from entpy.observer.base import Observer
from entpy.observer.registry import get_observer_registry
from entpy.schema.base import Schema


def _observer_package_for_module(mod: str) -> str | None:
    if not mod or mod == "__main__":
        return None
    if mod.endswith(".schemas"):
        return mod[: -len(".schemas")] + ".observers"
    if ".models" in mod:
        # examples.start.models.user -> examples.start.observers
        root = mod.split(".models", 1)[0]
        return f"{root}.observers"
    parent = mod.rsplit(".", 1)[0]
    return f"{parent}.observers"


def infer_observer_packages(schemas: list[type[Schema]]) -> list[str]:
    """从 Model/Schema 模块路径推断 ``{parent}.observers`` 包名。"""
    packages: list[str] = []
    seen: set[str] = set()
    for cls in schemas:
        pkg = _observer_package_for_module(cls.__module__)
        if pkg is not None and pkg not in seen:
            seen.add(pkg)
            packages.append(pkg)
    return packages


def _iter_observer_classes(module) -> Iterable[type[Observer]]:
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, Observer) and obj is not Observer:
            yield obj


def _load_package_observers(package_name: str) -> list[type[Observer]]:
    found: list[type[Observer]] = []
    try:
        pkg = importlib.import_module(package_name)
    except ImportError:
        return found
    if not hasattr(pkg, "__path__"):
        for cls in _iter_observer_classes(pkg):
            found.append(cls)
        return found
    for info in pkgutil.iter_modules(pkg.__path__, prefix=f"{package_name}."):
        try:
            mod = importlib.import_module(info.name)
        except ImportError:
            continue
        found.extend(_iter_observer_classes(mod))
    return found


def discover_observers(
    schemas: list[type[Schema]],
    *,
    observer_packages: list[str] | None = None,
) -> list[Observer]:
    """解析并实例化与 ``schemas`` 匹配的 Observer（先 @observes，再包扫描）。"""
    by_name = {s.__name__: s for s in schemas}
    registry = get_observer_registry()
    resolved: dict[str, Observer] = {}

    for schema in schemas:
        observer_cls = registry.get(schema)
        if observer_cls is not None:
            resolved[schema.__name__] = observer_cls(schema)

    packages = observer_packages if observer_packages is not None else infer_observer_packages(schemas)
    for pkg in packages:
        for observer_cls in _load_package_observers(pkg):
            schema_name = observer_cls.schema_name()
            if schema_name is None or schema_name not in by_name:
                continue
            if schema_name in resolved:
                continue
            schema_type = by_name[schema_name]
            if observer_cls.schema is None:
                observer_cls.schema = schema_type
            resolved[schema_name] = observer_cls(schema_type)

    return list(resolved.values())
