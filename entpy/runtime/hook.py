"""Hook / Mutator 链（对应 ent Hook 模型）。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from entpy.runtime.mutation import Mutation


class Mutator(Protocol):
    def mutate(self, mutation: Mutation) -> Any: ...


class AsyncMutator(Protocol):
    async def mutate(self, mutation: Mutation) -> Any: ...


MutatorFunc = Callable[[Mutator, Mutation], Any]
AsyncMutatorFunc = Callable[[AsyncMutator, Mutation], Awaitable[Any]]


class Hook:
    """将 mutator 函数包装进洋葱链。"""

    def __init__(self, fn: MutatorFunc) -> None:
        self._fn = fn

    def __call__(self, next_mutator: Mutator) -> Mutator:
        return _ChainMutator(self._fn, next_mutator)


class _ChainMutator:
    def __init__(self, fn: MutatorFunc, next_m: Mutator) -> None:
        self._fn = fn
        self._next = next_m

    def mutate(self, mutation: Mutation) -> Any:
        return self._fn(self._next, mutation)


class _TerminalMutator:
    """链尾 — 构建器中 hooks 之后执行实际持久化。"""

    def mutate(self, mutation: Mutation) -> Mutation:
        return mutation


def chain_hooks(hooks: list[Hook], mutation: Mutation) -> Mutation:
    """执行 hook 链；返回可能已修改的 mutation。"""
    mutator: Mutator = _TerminalMutator()
    for h in reversed(hooks):
        mutator = h(mutator)
    result = mutator.mutate(mutation)
    if isinstance(result, Mutation):
        return result
    return mutation


def hook(fn: MutatorFunc) -> Hook:
    """装饰器：@hook def my_hook(next, m): ..."""

    return Hook(fn)
