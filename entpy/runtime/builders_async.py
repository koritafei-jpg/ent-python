"""异步构建器。"""

from __future__ import annotations

from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph_async
from entpy.dialect.sqlalchemy.spec import DeleteSpec, QuerySpec
from entpy.entql.filter import entql_to_predicates
from entpy.runtime.builders import CreateBuilder, UpdateBuilder, _is_gremlin
from entpy.runtime.entity import Entity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.hook import chain_hooks
from entpy.runtime.interceptor import QueryRequest
from entpy.runtime.mutation import Mutation, Op
from entpy.runtime.spec_helpers import create_spec, update_spec
from entpy.privacy.policy import eval_mutation, eval_query
from entpy.runtime.predicate import Predicate
from entpy.schema.base import Schema


class AsyncCreateBuilder(CreateBuilder):
    async def save(self) -> Entity:
        self._validate_fields()
        mutation = Mutation(self._schema, Op.CREATE, fields=dict(self._fields), edges=dict(self._edges))
        mutation = chain_hooks(self._client._hooks, mutation)
        eval_mutation(self._client._ctx, self._client._policies, mutation)
        spec = create_spec(self._client._registry, self._schema, self._fields, self._edges)
        if _is_gremlin(self._client):
            from entpy.dialect.gremlin import graph_ops

            row_id = await self._client._driver.run(
                lambda: graph_ops.create_node(
                    self._client._driver.g, self._client._registry, spec
                )
            )
        else:
            async with self._client._driver.session() as session:
                row_id = await sqlgraph_async.create_node(
                    session, self._client._registry.tables, spec
                )
        return Entity(self._schema, {**self._fields, "id": row_id}, self._client)


class AsyncUpdateBuilder(UpdateBuilder):
    async def save(self) -> Entity:
        mutation = Mutation(
            self._schema, Op.UPDATE_ONE, id=self._id, fields=self._fields, edges=self._edges
        )
        mutation = chain_hooks(self._client._hooks, mutation)
        eval_mutation(self._client._ctx, self._client._policies, mutation)
        spec = update_spec(self._client._registry, self._schema, self._id, self._fields, self._edges)
        if _is_gremlin(self._client):
            from entpy.dialect.gremlin import graph_ops

            await self._client._driver.run(
                lambda: graph_ops.update_node(
                    self._client._driver.g, self._client._registry, spec
                )
            )
        else:
            async with self._client._driver.session() as session:
                await sqlgraph_async.update_node(
                    session, self._client._registry.tables, spec
                )
        return await self._client.query(self._schema).where(
            self._client.F(self._schema).id.eq(self._id)
        ).only()


class AsyncQueryBuilder:
    def __init__(self, client: Any, schema: type[Schema]) -> None:
        self._client = client
        self._schema = schema
        self._predicates: list[Predicate] = []
        self._limit: int | None = None
        self._with: list[str] = []

    def where(self, *preds: Predicate) -> AsyncQueryBuilder:
        self._predicates.extend(preds)
        return self

    def entql(self, filter_obj: dict) -> AsyncQueryBuilder:
        self._predicates.extend(entql_to_predicates(self._client.F(self._schema), filter_obj))
        return self

    def limit(self, n: int) -> AsyncQueryBuilder:
        self._limit = n
        return self

    def with_(self, *edges: str) -> AsyncQueryBuilder:
        self._with.extend(edges)
        return self

    async def all(self) -> list[Entity]:
        request = QueryRequest(
            schema=self._schema,
            limit=self._limit,
            with_edges=list(self._with),
        )
        eval_query(self._client._ctx, self._client._policies, request)
        label = self._client._registry.label_for(self._schema)
        if _is_gremlin(self._client):
            from entpy.dialect.gremlin import graph_ops

            spec = QuerySpec(
                table=label,
                limit=self._limit,
                with_edges=list(self._with),
            )
            rows = await self._client._driver.run(
                lambda: graph_ops.query_nodes(
                    self._client._driver.g,
                    self._client._registry,
                    spec,
                    gremlin_preds=list(self._predicates),
                )
            )
        else:
            table = self._client._registry.table_for(self._schema)
            sql_preds = [p.apply(table) for p in self._predicates]
            spec = QuerySpec(
                table=table.name,
                predicates=sql_preds,
                limit=self._limit,
                with_edges=list(self._with),
            )
            async with self._client._driver.session() as session:
                rows = await sqlgraph_async.query_nodes(
                    session, self._client._registry.tables, spec
                )
        return [Entity(self._schema, r, self._client) for r in rows]

    async def only(self) -> Entity:
        rows = await self.limit(2).all()
        if not rows:
            raise NotFoundError(f"{self._schema.type_name()}: not found")
        if len(rows) > 1:
            raise NotFoundError(f"{self._schema.type_name()}: not unique")
        return rows[0]


class AsyncDeleteBuilder:
    def __init__(self, client: Any, schema: type[Schema]) -> None:
        self._client = client
        self._schema = schema
        self._ids: list[int] = []
        self._predicates: list[Predicate] = []

    def where(self, *preds: Predicate) -> AsyncDeleteBuilder:
        self._predicates.extend(preds)
        return self

    def one(self, id: int) -> AsyncDeleteBuilder:
        self._ids = [id]
        return self

    async def execute(self) -> int:
        if self._predicates and not self._ids:
            rows = await self._client.query(self._schema).where(*self._predicates).all()
            self._ids = [r.id for r in rows]
        if not self._ids:
            raise ValueError("delete requires one(id) or where")
        label = self._client._registry.label_for(self._schema)
        if _is_gremlin(self._client):
            from entpy.dialect.gremlin import graph_ops

            spec = DeleteSpec(table=label, ids=self._ids)
            return await self._client._driver.run(
                lambda: graph_ops.delete_nodes(
                    self._client._driver.g, self._client._registry, spec
                )
            )
        table = self._client._registry.table_for(self._schema)
        spec = DeleteSpec(table=table.name, ids=self._ids)
        async with self._client._driver.session() as session:
            return await sqlgraph_async.delete_nodes(
                session, self._client._registry.tables, spec
            )
