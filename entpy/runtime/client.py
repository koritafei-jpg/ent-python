"""运行时 Client — 由 Schema 驱动数据库访问。"""

from __future__ import annotations

import re
from typing import Any

from entpy.dialect.sqlalchemy.driver import SQLAlchemyDriver
from entpy.dialect.sqlalchemy.metadata import build_metadata
from entpy.dialect.sqlalchemy.migrate import create_schema
from entpy.dialect.sqlalchemy.spec import DeleteSpec, QuerySpec
from entpy.dialect.sqlalchemy import sqlgraph
from entpy.ir.policies import collect_hooks, collect_interceptors, collect_policies
from entpy.runtime.builders import CreateBuilder, DeleteBuilder, QueryBuilder, UpdateBuilder
from entpy.runtime.registry import Registry
from entpy.runtime.predicate import PredicateFactory
from entpy.runtime.spec_helpers import create_spec, update_spec
from entpy.runtime.traverse import TraverseQuery
from entpy.schema.base import Schema


class Client:
    def __init__(
        self,
        driver: Any,
        registry: Registry,
        *,
        hooks: list | None = None,
        interceptors: list | None = None,
        policies: list | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> None:
        self._driver = driver
        self._registry = registry
        self._hooks = hooks or []
        self._interceptors = interceptors or []
        self._policies = policies or []
        self._ctx = ctx if ctx is not None else {}

    def migrate(self) -> None:
        """根据 Schema 图创建数据库表（DDL）。"""
        if self._registry.storage == "gremlin":
            return
        meta, _ = build_metadata(self._registry.graph)
        create_schema(self._driver.engine, meta)

    @classmethod
    def open(
        cls,
        dsn: str,
        *,
        schemas: list[type[Schema]],
        storage: str = "sql",
        ctx: dict[str, Any] | None = None,
        **engine_kw: Any,
    ) -> Client:
        registry = Registry.from_schemas(schemas, storage=storage)
        driver: Any
        if storage == "gremlin":
            from entpy.dialect.gremlin.driver import GremlinDriver

            driver = GremlinDriver.from_url(dsn, registry=registry)
        else:
            driver = SQLAlchemyDriver.from_url(dsn, **engine_kw)
        hooks = collect_hooks(schemas)
        return cls(
            driver,
            registry,
            hooks=hooks,
            interceptors=collect_interceptors(schemas),
            policies=collect_policies(schemas),
            ctx=ctx,
        )

    @classmethod
    def open_with(
        cls,
        dsn: str,
        *,
        schemas: list[type[Schema]],
        hooks: list | None = None,
        interceptors: list | None = None,
        policies: list | None = None,
        ctx: dict[str, Any] | None = None,
        **engine_kw: Any,
    ) -> Client:
        registry = Registry.from_schemas(schemas, storage="sql")
        driver = SQLAlchemyDriver.from_url(dsn, **engine_kw)
        return cls(
            driver,
            registry,
            hooks=(hooks or []) + collect_hooks(schemas),
            interceptors=(interceptors or []) + collect_interceptors(schemas),
            policies=(policies or []) + collect_policies(schemas),
            ctx=ctx,
        )

    def F(self, schema: type[Schema]) -> PredicateFactory:
        return self._registry.F(schema)

    def create(self, schema: type[Schema], /, **fields: Any) -> CreateBuilder:
        return CreateBuilder(self, schema, fields)

    def query(self, schema: type[Schema]) -> QueryBuilder:
        return QueryBuilder(self, schema)

    def update(self, schema: type[Schema], id: int) -> UpdateBuilder:
        return UpdateBuilder(self, schema, id)

    def delete(self, schema: type[Schema]) -> DeleteBuilder:
        return DeleteBuilder(self, schema)

    def traverse(self, entity: Any, edge: str | None = None) -> TraverseQuery:
        hops = [edge] if edge else None
        return TraverseQuery(self, entity, hops)

    def node(self, schema: type[Schema]) -> NodeClient:
        return NodeClient(self, schema)

    def __getattr__(self, name: str) -> NodeClient:
        for schema in self._registry.nodes:
            if _snake(schema.type_name()) == name:
                return NodeClient(self, schema)
        raise AttributeError(name)

    def search(self, schema: type[Schema]):
        from entpy.search.builder import SearchBuilder
        from entpy.search.registry import SearchRegistry

        sr = SearchRegistry.from_registry(self._registry)
        return SearchBuilder(self, schema, sr)  # 测试中可覆盖 bm25_backend

class NodeClient:
    def __init__(self, client: Client, schema: type[Schema]) -> None:
        self._client = client
        self._schema = schema

    def create(self, /, **fields: Any) -> CreateBuilder:
        return self._client.create(self._schema, **fields)

    def query(self) -> QueryBuilder:
        return self._client.query(self._schema)

    def update(self, id: int) -> UpdateBuilder:
        return self._client.update(self._schema, id)

    def delete(self) -> DeleteBuilder:
        return self._client.delete(self._schema)


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
