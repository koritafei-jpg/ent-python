"""Hook / Mutator 链（同步 Hook 与原生 AsyncHook）。"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any, Awaitable, Callable, Protocol

from entpy.runtime.mutation import Mutation


class Mutator(Protocol):
    def mutate(self, mutation: Mutation) -> Any: ...


class AsyncMutator(Protocol):
    async def mutate(self, mutation: Mutation) -> Any: ...


MutatorFunc = Callable[[Mutator, Mutation], Any]
AsyncMutatorFunc = Callable[[AsyncMutator, Mutation], Awaitable[Any]]


class Hook:
    """同步 Hook：``@Hook def fn(next, m): ...``"""

    def __init__(self, fn: MutatorFunc) -> None:
        self._fn = fn

    def __call__(self, next_mutator: Mutator) -> Mutator:
        return _ChainMutator(self._fn, next_mutator)


class AsyncHook:
    """异步 Hook：``@AsyncHook async def fn(next, m): ...``"""

    def __init__(self, fn: AsyncMutatorFunc) -> None:
        self._fn = fn

    def __call__(self, next_mutator: AsyncMutator) -> AsyncMutator:
        return _AsyncChainMutator(self._fn, next_mutator)


class _ChainMutator:
    def __init__(self, fn: MutatorFunc, next_m: Mutator) -> None:
        self._fn = fn
        self._next = next_m

    def mutate(self, mutation: Mutation) -> Any:
        return self._fn(self._next, mutation)


class _AsyncChainMutator:
    def __init__(self, fn: AsyncMutatorFunc, next_m: AsyncMutator) -> None:
        self._fn = fn
        self._next = next_m

    async def mutate(self, mutation: Mutation) -> Any:
        return await self._fn(self._next, mutation)


class _TerminalMutator:
    def mutate(self, mutation: Mutation) -> Mutation:
        return mutation


class _AsyncTerminalMutator:
    async def mutate(self, mutation: Mutation) -> Mutation:
        return mutation


class _SyncHookOnAsync:
    """将同步 Hook 接入异步链（仅该 Hook 在线程池执行）。"""

    def __init__(self, hook: Hook, next_m: AsyncMutator) -> None:
        self._hook = hook
        self._next = next_m

    async def mutate(self, mutation: Mutation) -> Any:
        def run() -> Any:
            sync_mutator = self._hook(_AsyncMutatorAsSync(self._next))
            return sync_mutator.mutate(mutation)

        result = await asyncio.to_thread(run)
        if isinstance(result, Mutation):
            return result
        raise TypeError(
            f"hook must return Mutation, got {type(result).__name__}"
        )


def _run_coro_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """从同步上下文执行协程；若当前线程已有 event loop 则在新线程内运行。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class _AsyncMutatorAsSync:
    """在线程内让同步 Hook 可 ``await`` 后续的 AsyncMutator。"""

    def __init__(self, async_mutator: AsyncMutator) -> None:
        self._async_mutator = async_mutator

    def mutate(self, mutation: Mutation) -> Any:
        return _run_coro_sync(self._async_mutator.mutate(mutation))


class _SyncMutatorOnAsync:
    """异步链中调用后续同步 mutator。"""

    def __init__(self, sync_mutator: Mutator) -> None:
        self._sync_mutator = sync_mutator

    async def mutate(self, mutation: Mutation) -> Any:
        return await asyncio.to_thread(self._sync_mutator.mutate, mutation)


def chain_hooks(hooks: list[Any], mutation: Mutation) -> Mutation:
    """执行同步 hook 链。"""
    mutator: Mutator = _TerminalMutator()
    for h in reversed(hooks):
        if isinstance(h, AsyncHook):
            raise TypeError(
                "AsyncHook cannot run in sync chain_hooks; use chain_hooks_async"
            )
        if not isinstance(h, Hook):
            raise TypeError(f"expected Hook, got {type(h).__name__}")
        mutator = h(mutator)
    result = mutator.mutate(mutation)
    if isinstance(result, Mutation):
        return result
    raise TypeError(
        f"hook must return Mutation, got {type(result).__name__}"
    )


async def chain_hooks_async(hooks: list[Any], mutation: Mutation) -> Mutation:
    """执行异步 hook 链；全为 AsyncHook 时原生 await，否则按 Hook 类型混合调度。"""
    if not hooks:
        return mutation

    mutator: AsyncMutator = _AsyncTerminalMutator()
    for h in reversed(hooks):
        if isinstance(h, AsyncHook):
            mutator = h(mutator)
        elif isinstance(h, Hook):
            mutator = _SyncHookOnAsync(h, mutator)  # type: ignore[assignment]
        else:
            raise TypeError(f"expected Hook or AsyncHook, got {type(h).__name__}")

    result = await mutator.mutate(mutation)
    if isinstance(result, Mutation):
        return result
    raise TypeError(
        f"hook must return Mutation, got {type(result).__name__}"
    )


def hook(fn: MutatorFunc) -> Hook:
    return Hook(fn)


def async_hook(fn: AsyncMutatorFunc) -> AsyncHook:
    return AsyncHook(fn)


def is_async_hook(h: Any) -> bool:
    return isinstance(h, AsyncHook)
