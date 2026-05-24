"""从 Schema 收集 hooks、拦截器与 privacy 策略。"""

from __future__ import annotations

from entpy.schema.base import Mixin, Schema
from entpy.runtime.hook import Hook
from entpy.runtime.interceptor import Interceptor
from entpy.privacy.policy import Policy
from entpy.observer.integration import setup_observers


def collect_hooks(schemas: list[type[Schema]]) -> list[Hook]:
    hooks: list[Hook] = []
    for cls in schemas:
        for mixin in cls.mixins():
            if issubclass(mixin, Mixin):
                for h in mixin.hooks():
                    if isinstance(h, Hook):
                        hooks.append(h)
        for h in cls.hooks():
            if isinstance(h, Hook):
                hooks.append(h)
    return hooks


def collect_runtime_hooks(
    schemas: list[type[Schema]],
    *,
    observer_packages: list[str] | None = None,
    extra_hooks: list[Hook] | None = None,
) -> tuple[list[Hook], list]:
    """Schema hooks + 自动发现的 Observer hooks。"""
    schema_hooks = collect_hooks(schemas)
    return setup_observers(
        schemas,
        observer_packages=observer_packages,
        extra_hooks=(extra_hooks or []) + schema_hooks,
    )


def collect_interceptors(schemas: list[type[Schema]]) -> list[Interceptor]:
    inters: list[Interceptor] = []
    for cls in schemas:
        for mixin in cls.mixins():
            if issubclass(mixin, Mixin):
                for i in mixin.interceptors():
                    if isinstance(i, Interceptor):
                        inters.append(i)
        for i in cls.interceptors():
            if isinstance(i, Interceptor):
                inters.append(i)
    return inters


def collect_policies(schemas: list[type[Schema]]) -> list[Policy]:
    policies: list[Policy] = []
    for cls in schemas:
        for mixin in cls.mixins():
            if issubclass(mixin, Mixin):
                p = mixin.policy()
                if isinstance(p, Policy):
                    policies.append(p)
        p = cls.policy()
        if isinstance(p, Policy):
            policies.append(p)
    return policies
