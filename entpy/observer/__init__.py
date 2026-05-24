"""Schema 生命周期 Observer（自动发现注册，Schema 侧零依赖）。"""

from entpy.observer.base import Observer, observes
from entpy.observer.discovery import discover_observers, infer_observer_packages
from entpy.observer.registry import ObserverRegistry, get_observer_registry

__all__ = [
    "Observer",
    "observes",
    "ObserverRegistry",
    "get_observer_registry",
    "discover_observers",
    "infer_observer_packages",
]
