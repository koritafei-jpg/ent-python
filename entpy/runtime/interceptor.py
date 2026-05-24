"""查询拦截器（同步 / 异步链）。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field as dc_field
from typing import Any, Awaitable, Callable, Protocol

from entpy.schema.base import Schema


@dataclass
class QueryRequest:
    schema: type[Schema]
    predicates: list[Any] = dc_field(default_factory=list)
    limit: int | None = None
    with_edges: list[str] = dc_field(default_factory=list)


class Querier(Protocol):
    def query(self, request: QueryRequest) -> list[dict[str, Any]]: ...


class AsyncQuerier(Protocol):
    async def query(self, request: QueryRequest) -> list[dict[str, Any]]: ...


InterceptorFunc = Callable[[Querier, QueryRequest], list[dict[str, Any]]]
AsyncInterceptorFunc = Callable[
    [AsyncQuerier, QueryRequest], Awaitable[list[dict[str, Any]]]
]


class Interceptor:
    def __init__(self, fn: InterceptorFunc) -> None:
        self._fn = fn

    def __call__(self, next_q: Querier) -> Querier:
        return _ChainQuerier(self._fn, next_q)


class AsyncInterceptor:
    """原生异步拦截器：``async def fn(next_q, req): return await next_q.query(req)``"""

    def __init__(self, fn: AsyncInterceptorFunc) -> None:
        self._fn = fn

    def __call__(self, next_q: AsyncQuerier) -> AsyncQuerier:
        return _AsyncChainQuerier(self._fn, next_q)


class _ChainQuerier:
    def __init__(self, fn: InterceptorFunc, next_q: Querier) -> None:
        self._fn = fn
        self._next = next_q

    def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        return self._fn(self._next, request)


class _AsyncChainQuerier:
    def __init__(self, fn: AsyncInterceptorFunc, next_q: AsyncQuerier) -> None:
        self._fn = fn
        self._next = next_q

    async def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        return await self._fn(self._next, request)


class _TerminalQuerier:
    def __init__(self, execute: Callable[[QueryRequest], list[dict[str, Any]]]) -> None:
        self._execute = execute

    def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        return self._execute(request)


class _AsyncTerminalQuerier:
    def __init__(
        self,
        execute: Callable[[QueryRequest], Awaitable[list[dict[str, Any]]]],
    ) -> None:
        self._execute = execute

    async def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        return await self._execute(request)


class _SyncInterceptorOnAsync:
    """将同步 Interceptor 接入异步链（仅该层在线程池执行）。"""

    def __init__(self, interceptor: Interceptor, next_q: AsyncQuerier) -> None:
        self._interceptor = interceptor
        self._next = next_q

    async def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        async_next = _AsyncQuerierAsSync(self._next)

        def run() -> list[dict[str, Any]]:
            sync_terminal = _TerminalQuerier(async_next.query_sync)
            chained = self._interceptor(sync_terminal)
            return chained.query(request)

        return await asyncio.to_thread(run)


class _AsyncQuerierAsSync:
    def __init__(self, async_q: AsyncQuerier) -> None:
        self._async_q = async_q

    def query_sync(self, request: QueryRequest) -> list[dict[str, Any]]:
        from entpy.runtime.hook import _run_coro_sync

        return _run_coro_sync(self._async_q.query(request))


def chain_interceptors(
    interceptors: list[Interceptor],
    execute: Callable[[QueryRequest], list[dict[str, Any]]],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    querier: Querier = _TerminalQuerier(execute)
    for i in reversed(interceptors):
        querier = i(querier)
    return querier.query(request)


async def chain_interceptors_async(
    interceptors: list[Any],
    execute: Callable[[QueryRequest], Awaitable[list[dict[str, Any]]]],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    """异步拦截器链；同步 ``Interceptor`` 自动包一层 ``to_thread``。"""
    querier: AsyncQuerier = _AsyncTerminalQuerier(execute)
    for i in reversed(interceptors):
        if isinstance(i, AsyncInterceptor):
            querier = i(querier)
        elif isinstance(i, Interceptor):
            querier = _SyncInterceptorOnAsync(i, querier)  # type: ignore[assignment]
        else:
            raise TypeError(
                f"expected Interceptor or AsyncInterceptor, got {type(i).__name__}"
            )
    return await querier.query(request)
