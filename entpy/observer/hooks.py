"""将 Observer 生命周期方法适配为 Hook 链。"""

from __future__ import annotations

from entpy.observer.base import Observer
from entpy.runtime.hook import Hook, hook
from entpy.runtime.mutation import Mutation, Op


_BEFORE: dict[Op, str] = {
    Op.CREATE: "creating",
    Op.UPDATE_ONE: "updating",
    Op.DELETE: "deleting",
    Op.DELETE_ONE: "deleting",
}

_AFTER: dict[Op, str] = {
    Op.CREATE: "created",
    Op.UPDATE_ONE: "updated",
    Op.DELETE: "deleted",
    Op.DELETE_ONE: "deleted",
}


def _is_overridden(observer: Observer, method_name: str) -> bool:
    impl = getattr(observer, method_name, None)
    base = getattr(Observer, method_name, None)
    if impl is None or base is None:
        return False
    return getattr(impl, "__func__", impl) is not base


def observers_to_hooks(observers: list[Observer]) -> list[Hook]:
    hooks: list[Hook] = []
    for observer in observers:
        for op, method_name in _BEFORE.items():
            if not _is_overridden(observer, method_name):
                continue
            method = getattr(observer, method_name)
            hooks.append(_make_before_hook(observer, op, method))
    return hooks


def _make_before_hook(observer: Observer, op: Op, method) -> Hook:
    @hook
    def _before(next_mutator, mutation: Mutation):
        if mutation.schema is not observer.schema_type or mutation.op is not op:
            return next_mutator.mutate(mutation)
        method(mutation)
        return next_mutator.mutate(mutation)

    return _before


def notify_after_observers(observers: list[Observer], mutation: Mutation) -> None:
    method_name = _AFTER.get(mutation.op)
    if method_name is not None:
        for observer in observers:
            if mutation.schema is not observer.schema_type:
                continue
            if not _is_overridden(observer, method_name):
                continue
            getattr(observer, method_name)(mutation)

    if mutation.op in (Op.CREATE, Op.UPDATE_ONE):
        for observer in observers:
            if mutation.schema is not observer.schema_type:
                continue
            if _is_overridden(observer, "on_save"):
                observer.on_save(mutation)
    elif mutation.op in (Op.DELETE, Op.DELETE_ONE):
        for observer in observers:
            if mutation.schema is not observer.schema_type:
                continue
            if _is_overridden(observer, "on_delete"):
                observer.on_delete(mutation)
