"""异步运行时 Client。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from entpy.dialect.sqlalchemy.async_driver import AsyncSQLAlchemyDriver
from entpy.dialect.sqlalchemy.metadata import build_metadata
from entpy.dialect.sqlalchemy.migrate import create_schema
from entpy.ir.policies import collect_interceptors, collect_policies, collect_runtime_hooks
from entpy.runtime.builders_async import (
    AsyncCreateBuilder,
    AsyncDeleteBuilder,
    AsyncQueryBuilder,
    AsyncUpdateBuilder,
)
from entpy.runtime.client import NodeClient, _snake
from entpy.runtime.registry import Registry
from entpy.schema.base import Schema
from entpy.runtime.predicate import PredicateFactory


class AsyncClient:
    def __init__(
        self,
        driver: Any,
        registry: Registry,
        *,
        hooks: list | None = None,
        interceptors: list | None = None,
        policies: list | None = None,
        observers: list | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> None:
        self._driver = driver
        self._registry = registry
        self._hooks = hooks or []
        self._interceptors = interceptors or []
        self._policies = policies or []
        self._observers = observers or []
        self._ctx = ctx if ctx is not None else {}
        self._search_registry: Any = None

    async def migrate(self) -> None:
        """根据 Schema 图创建数据库表（DDL）。"""
        if self._registry.storage == "gremlin":
            return
        meta, _ = build_metadata(self._registry.graph)

        async def _run(conn):
            await conn.run_sync(lambda sync_conn: meta.create_all(bind=sync_conn))

        async with self._driver.engine.begin() as conn:
            if self._driver.dialect() == "postgresql":
                from sqlalchemy import text
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await _run(conn)

    @asynccontextmanager
    async def ascope(self, ctx: dict[str, Any] | None = None) -> AsyncIterator[AsyncClient]:
        """将本 AsyncClient 绑定到当前异步上下文；不释放连接池。"""
        from entpy.active.context import (
            push_scope_ctx,
            reset_async_client,
            reset_scope_ctx,
            set_async_client,
        )

        ctx_token = push_scope_ctx(ctx) if ctx else None
        token = set_async_client(self)
        try:
            yield self
        finally:
            reset_async_client(token)
            if ctx_token is not None:
                reset_scope_ctx(ctx_token)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """块内所有写操作共用同一 async session，块末一次 commit。"""
        from entpy.runtime.session_scope import async_transaction

        async with async_transaction(self._driver):
            yield

    async def aclose(self) -> None:
        if self._registry.storage == "gremlin":
            self._driver.close()
        elif hasattr(self._driver, "engine"):
            await self._driver.engine.dispose()

    def traverse(self, entity: Any, edge: str | None = None) -> Any:
        from entpy.runtime.traverse import AsyncTraverseChain

        hops = [edge] if edge else None
        return AsyncTraverseChain(self, entity, hops)

    @classmethod
    def open(
        cls,
        dsn: str,
        *,
        schemas: list[type[Schema]],
        storage: str = "sql",
        observer_packages: list[str] | None = None,
        ctx: dict[str, Any] | None = None,
        **engine_kw: Any,
    ) -> AsyncClient:
        registry = Registry.from_schemas(schemas, storage=storage)
        driver: Any
        if storage == "gremlin":
            from entpy.dialect.gremlin.driver import GremlinDriver

            driver = GremlinDriver.from_url(dsn, registry=registry)
        else:
            driver = AsyncSQLAlchemyDriver.from_url(dsn, **engine_kw)
        hooks, observers = collect_runtime_hooks(
            schemas, observer_packages=observer_packages
        )
        return cls(
            driver,
            registry,
            hooks=hooks,
            observers=observers,
            interceptors=collect_interceptors(schemas),
            policies=collect_policies(schemas),
            ctx=ctx,
        )

    def F(self, schema: type[Schema]) -> PredicateFactory:
        return self._registry.F(schema)

    def create(self, schema: type[Schema], /, **fields: Any) -> AsyncCreateBuilder:
        return AsyncCreateBuilder(self, schema, fields)

    def query(self, schema: type[Schema]) -> AsyncQueryBuilder:
        return AsyncQueryBuilder(self, schema)

    def update(self, schema: type[Schema], id: Any) -> AsyncUpdateBuilder:
        return AsyncUpdateBuilder(self, schema, id)

    def delete(self, schema: type[Schema]) -> AsyncDeleteBuilder:
        return AsyncDeleteBuilder(self, schema)

    def _get_search_registry(self):
        if self._search_registry is None:
            from entpy.search.registry import SearchRegistry

            self._search_registry = SearchRegistry.from_registry(self._registry)
        return self._search_registry

    def search(self, schema: type[Schema]):
        from entpy.search.builder import SearchBuilder

        return SearchBuilder(self, schema, self._get_search_registry())

    def __getattr__(self, name: str) -> _AsyncNodeClient:
        for schema in self._registry.nodes:
            if _snake(schema.type_name()) == name:
                return _AsyncNodeClient(self, schema)
        raise AttributeError(name)

class _AsyncNodeClient:
    def __init__(self, client: AsyncClient, schema: type[Schema]) -> None:
        self._client = client
        self._schema = schema

    def create(self, /, **fields: Any) -> AsyncCreateBuilder:
        return self._client.create(self._schema, **fields)

    def query(self) -> AsyncQueryBuilder:
        return self._client.query(self._schema)

    def update(self, id: Any) -> AsyncUpdateBuilder:
        return self._client.update(self._schema, id)

    def delete(self) -> AsyncDeleteBuilder:
        return self._client.delete(self._schema)
