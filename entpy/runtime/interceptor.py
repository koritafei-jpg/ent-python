"""查询拦截器。"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Protocol

from entpy.schema.base import Schema


@dataclass
class QueryRequest:
    schema: type[Schema]
    predicates: list[Any] = dc_field(default_factory=list)
    limit: int | None = None
    with_edges: list[str] = dc_field(default_factory=list)


class Querier(Protocol):
    def query(self, request: QueryRequest) -> list[dict[str, Any]]: ...


InterceptorFunc = Callable[[Querier, QueryRequest], list[dict[str, Any]]]


class Interceptor:
    def __init__(self, fn: InterceptorFunc) -> None:
        self._fn = fn

    def __call__(self, next_q: Querier) -> Querier:
        return _ChainQuerier(self._fn, next_q)


class _ChainQuerier:
    def __init__(self, fn: InterceptorFunc, next_q: Querier) -> None:
        self._fn = fn
        self._next = next_q

    def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        return self._fn(self._next, request)


class _TerminalQuerier:
    def __init__(self, execute: Callable[[QueryRequest], list[dict[str, Any]]]) -> None:
        self._execute = execute

    def query(self, request: QueryRequest) -> list[dict[str, Any]]:
        return self._execute(request)


def chain_interceptors(
    interceptors: list[Interceptor],
    execute: Callable[[QueryRequest], list[dict[str, Any]]],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    querier: Querier = _TerminalQuerier(execute)
    for i in reversed(interceptors):
        querier = i(querier)
    return querier.query(request)
