"""异步构建器。"""

from __future__ import annotations

from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph_async
from entpy.dialect.sqlalchemy.spec import DeleteSpec
from entpy.entql.filter import entql_to_predicates
from entpy.observer.hooks import notify_after_observers
from entpy.privacy.policy import eval_mutation, eval_query
from entpy.runtime.builders import (
    CreateBuilder,
    UpdateBuilder,
    _is_gremlin,
    _is_noop_update,
)
from entpy.runtime.entity import Entity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.hook import chain_hooks_async
from entpy.runtime.interceptor import QueryRequest
from entpy.runtime.mutation import Mutation, Op
from entpy.runtime.predicate import Predicate
from entpy.runtime.query_exec import execute_query_async
from entpy.runtime.spec_helpers import create_spec, update_spec
from entpy.runtime.validation import (
    collect_update_fields_after_hooks,
    materialize_field_values,
    merge_mutation_into_builder,
    reject_immutable_updates,
    snapshot_edges,
)
from entpy.schema.base import Schema


class AsyncCreateBuilder(CreateBuilder):
    async def save(self) -> Entity:
        self._validate_fields()
        mutation = Mutation(
            self._schema,
            Op.CREATE,
            fields=dict(self._fields),
            edges=snapshot_edges(self._edges),
        )
        mutation = await chain_hooks_async(self._client._hooks, mutation)
        merge_mutation_into_builder(mutation, fields=self._fields, edges=self._edges)
        from entpy.active.context import get_effective_ctx

        eval_mutation(get_effective_ctx(self._client), self._client._policies, mutation)
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
        mutation.id = row_id
        notify_after_observers(self._client._observers, mutation)
        row_data = materialize_field_values(
            self._client._registry,
            self._schema,
            {**self._fields, "id": row_id},
        )
        return Entity(self._schema, row_data, self._client)


async def _load_existing_entity_async(
    client: Any, schema: type[Schema], row_id: Any
) -> Entity:
    existing = await (
        client.query(schema)
        .where(client.F(schema).id.eq(row_id))
        .first()
    )
    if existing is None:
        raise NotFoundError(f"{schema.type_name()}: not found")
    return existing


class AsyncUpdateBuilder(UpdateBuilder):
    async def save(self) -> Entity:
        reject_immutable_updates(self._client._registry, self._schema, self._fields)
        mutation = Mutation(
            self._schema,
            Op.UPDATE_ONE,
            id=self._id,
            fields=dict(self._fields),
            edges=snapshot_edges(self._edges),
        )
        mutation = await chain_hooks_async(self._client._hooks, mutation)
        self._fields = collect_update_fields_after_hooks(
            self._schema, mutation, self._explicit_fields
        )
        merge_mutation_into_builder(mutation, fields={}, edges=self._edges)
        from entpy.active.context import get_effective_ctx

        eval_mutation(get_effective_ctx(self._client), self._client._policies, mutation)
        if _is_noop_update(self._fields, self._edges):
            return await _load_existing_entity_async(
                self._client, self._schema, self._id
            )
        spec = update_spec(self._client._registry, self._schema, self._id, self._fields, self._edges)
        if _is_gremlin(self._client):
            from entpy.dialect.gremlin import graph_ops

            def _run():
                return graph_ops.update_node(
                    self._client._driver.g, self._client._registry, spec
                )

            row = await self._client._driver.run(_run)
        else:
            async with self._client._driver.session() as session:
                row = await sqlgraph_async.update_node(
                    session, self._client._registry.tables, spec
                )
        if row is None:
            raise NotFoundError(f"{self._schema.type_name()}: not found")
        notify_after_observers(
            self._client._observers,
            Mutation(
                self._schema,
                Op.UPDATE_ONE,
                id=self._id,
                fields=dict(self._fields),
                edges=dict(self._edges),
            ),
        )
        row_data = materialize_field_values(
            self._client._registry, self._schema, dict(row)
        )
        return Entity(self._schema, row_data, self._client)


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
        from entpy.active.context import get_effective_ctx

        eval_query(get_effective_ctx(self._client), self._client._policies, request)
        rows = await execute_query_async(
            self._client,
            self._schema,
            self._predicates,
            limit=self._limit,
            with_edges=list(self._with),
            request=request,
        )
        return [Entity(self._schema, r, self._client) for r in rows]

    async def _query_with_limit(self, limit: int) -> list[Entity]:
        request = QueryRequest(
            schema=self._schema,
            limit=limit,
            with_edges=list(self._with),
        )
        from entpy.active.context import get_effective_ctx

        eval_query(get_effective_ctx(self._client), self._client._policies, request)
        rows = await execute_query_async(
            self._client,
            self._schema,
            self._predicates,
            limit=self._limit,
            with_edges=list(self._with),
            request=request,
        )
        return [Entity(self._schema, r, self._client) for r in rows]

    async def only(self) -> Entity:
        rows = await self._query_with_limit(2)
        if not rows:
            raise NotFoundError(f"{self._schema.type_name()}: not found")
        if len(rows) > 1:
            raise NotFoundError(f"{self._schema.type_name()}: not unique")
        return rows[0]

    async def first(self) -> Entity | None:
        rows = await self._query_with_limit(1)
        return rows[0] if rows else None


class AsyncDeleteBuilder:
    def __init__(self, client: Any, schema: type[Schema]) -> None:
        from entpy.schema.base import View

        if issubclass(schema, View):
            raise TypeError(f"{schema.type_name()} is a View")
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
        label = self._client._registry.label_for(self._schema)
        if self._ids and self._predicates:
            raise ValueError("delete: use one(id) or where(), not both")
        if not self._ids and not self._predicates:
            raise ValueError("delete requires one(id) or where")
        op = Op.DELETE_ONE if len(self._ids) == 1 else Op.DELETE
        mutation = Mutation(
            self._schema,
            op,
            id=self._ids[0] if len(self._ids) == 1 else None,
        )
        mutation = await chain_hooks_async(self._client._hooks, mutation)
        from entpy.active.context import get_effective_ctx

        eval_mutation(get_effective_ctx(self._client), self._client._policies, mutation)
        if _is_gremlin(self._client):
            from entpy.dialect.gremlin import graph_ops

            preds = list(self._predicates) if not self._ids else []
            spec = DeleteSpec(table=label, ids=self._ids, predicates=preds)
            count = await self._client._driver.run(
                lambda: graph_ops.delete_nodes(
                    self._client._driver.g, self._client._registry, spec
                )
            )
        else:
            table = self._client._registry.table_for(self._schema)
            sql_preds = [p.apply(table) for p in self._predicates] if not self._ids else []
            spec = DeleteSpec(table=table.name, ids=self._ids, predicates=sql_preds)
            async with self._client._driver.session() as session:
                count = await sqlgraph_async.delete_nodes(
                    session, self._client._registry.tables, spec
                )
        if count > 0:
            notify_after_observers(self._client._observers, mutation)
        return count
