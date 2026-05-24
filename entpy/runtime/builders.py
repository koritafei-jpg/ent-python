"""Create / Query / Update / Delete 构建器。"""

from __future__ import annotations

import json
from typing import Any

from entpy.dialect.sqlalchemy import sqlgraph
from entpy.dialect.sqlalchemy.spec import DeleteSpec
from entpy.entql.filter import entql_to_predicates
from entpy.observer.hooks import notify_after_observers
from entpy.privacy.policy import eval_mutation, eval_query
from entpy.runtime.entity import Entity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.hook import chain_hooks
from entpy.runtime.interceptor import QueryRequest
from entpy.runtime.mutation import Mutation, Op
from entpy.runtime.predicate import Predicate
from entpy.runtime.query_exec import execute_query_sync
from entpy.runtime.spec_helpers import create_spec, update_spec
from entpy.runtime.validation import (
    collect_update_fields_after_hooks,
    isolate_field_value,
    isolate_fields,
    materialize_field_values,
    merge_mutation_into_builder,
    reject_immutable_updates,
    snapshot_edges,
)
from entpy.schema.base import Schema, View


def _is_gremlin(client: Any) -> bool:
    return client._driver.dialect() == "gremlin"


class CreateBuilder:
    def __init__(self, client: Any, schema: type[Schema], initial: dict[str, Any] | None = None) -> None:
        if issubclass(schema, View):
            raise TypeError(f"{schema.type_name()} is a View")
        self._client = client
        self._schema = schema
        self._fields: dict[str, Any] = isolate_fields(schema, dict(initial or {}))
        self._edges: dict[str, list[Any]] = {}

    def set(self, name: str, value: Any) -> CreateBuilder:
        self._fields[name] = isolate_field_value(self._schema, name, value)
        return self

    def add(self, edge: str, *ids: Any) -> CreateBuilder:
        self._edges.setdefault(edge, []).extend(ids)
        return self

    def _validate_fields(self) -> None:
        from entpy.schema.field import FieldType

        node = self._client._registry.node_for(self._schema)
        for f in node.fields:
            if f.name not in self._fields and f.default is not None:
                self._fields[f.name] = f.default
            if f.name not in self._fields and f.default_func:
                self._fields[f.name] = f.default_func()
            if f.name in self._fields:
                for v in f.validators:
                    v(self._fields.get(f.name))
            if f.typ == FieldType.VECTOR and f.name in self._fields:
                val = self._fields[f.name]
                if isinstance(val, list) and self._client._driver.dialect() == "sqlite":
                    self._fields[f.name] = json.dumps(val)

    def save(self) -> Entity:
        self._validate_fields()
        mutation = Mutation(
            self._schema,
            Op.CREATE,
            fields=dict(self._fields),
            edges=snapshot_edges(self._edges),
        )
        mutation = chain_hooks(self._client._hooks, mutation)
        merge_mutation_into_builder(mutation, fields=self._fields, edges=self._edges)
        from entpy.active.context import get_effective_ctx

        eval_mutation(get_effective_ctx(self._client), self._client._policies, mutation)
        spec = create_spec(self._client._registry, self._schema, self._fields, self._edges)
        with self._client._driver.session() as session:
            if _is_gremlin(self._client):
                from entpy.dialect.gremlin import graph_ops

                row_id = graph_ops.create_node(
                    session.g, self._client._registry, spec
                )
            else:
                row_id = sqlgraph.create_node(
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


class QueryBuilder:
    def __init__(self, client: Any, schema: type[Schema]) -> None:
        self._client = client
        self._schema = schema
        self._predicates: list[Predicate] = []
        self._limit: int | None = None
        self._with: list[str] = []

    def where(self, *preds: Predicate) -> QueryBuilder:
        self._predicates.extend(preds)
        return self

    def entql(self, filter_obj: dict) -> QueryBuilder:
        self._predicates.extend(entql_to_predicates(self._client.F(self._schema), filter_obj))
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._limit = n
        return self

    def with_(self, *edges: str) -> QueryBuilder:
        self._with.extend(edges)
        return self

    def _run_query(self, request: QueryRequest) -> list[dict]:
        return execute_query_sync(
            self._client,
            self._schema,
            self._predicates,
            limit=self._limit,
            with_edges=list(self._with),
            request=request,
        )

    def all(self) -> list[Entity]:
        request = QueryRequest(
            schema=self._schema,
            limit=self._limit,
            with_edges=list(self._with),
        )
        from entpy.active.context import get_effective_ctx

        eval_query(get_effective_ctx(self._client), self._client._policies, request)
        rows = self._run_query(request)
        return [Entity(self._schema, r, self._client) for r in rows]

    def only(self) -> Entity:
        saved_limit = self._limit
        self._limit = 2
        try:
            rows = self.all()
        finally:
            self._limit = saved_limit
        if not rows:
            raise NotFoundError(f"{self._schema.type_name()}: not found")
        if len(rows) > 1:
            raise NotFoundError(f"{self._schema.type_name()}: not unique")
        return rows[0]

    def first(self) -> Entity | None:
        saved_limit = self._limit
        self._limit = 1
        try:
            rows = self.all()
        finally:
            self._limit = saved_limit
        return rows[0] if rows else None


class UpdateBuilder:
    def __init__(self, client: Any, schema: type[Schema], id: int) -> None:
        if issubclass(schema, View):
            raise TypeError(f"{schema.type_name()} is a View")
        self._client = client
        self._schema = schema
        self._id = id
        self._fields: dict[str, Any] = {}
        self._explicit_fields: set[str] = set()
        self._edges: dict[str, list[Any]] = {}

    def set(self, name: str, value: Any) -> UpdateBuilder:
        self._explicit_fields.add(name)
        self._fields[name] = isolate_field_value(self._schema, name, value)
        return self

    def add(self, edge: str, *ids: int) -> UpdateBuilder:
        self._edges.setdefault(edge, []).extend(ids)
        return self

    def save(self) -> Entity:
        reject_immutable_updates(self._client._registry, self._schema, self._fields)
        mutation = Mutation(
            self._schema,
            Op.UPDATE_ONE,
            id=self._id,
            fields=dict(self._fields),
            edges=snapshot_edges(self._edges),
        )
        mutation = chain_hooks(self._client._hooks, mutation)
        self._fields = collect_update_fields_after_hooks(
            self._schema, mutation, self._explicit_fields
        )
        merge_mutation_into_builder(mutation, fields={}, edges=self._edges)
        from entpy.active.context import get_effective_ctx

        eval_mutation(get_effective_ctx(self._client), self._client._policies, mutation)
        spec = update_spec(self._client._registry, self._schema, self._id, self._fields, self._edges)
        with self._client._driver.session() as session:
            if _is_gremlin(self._client):
                from entpy.dialect.gremlin import graph_ops

                row = graph_ops.update_node(
                    session.g, self._client._registry, spec
                )
            else:
                row = sqlgraph.update_node(
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


class DeleteBuilder:
    def __init__(self, client: Any, schema: type[Schema]) -> None:
        if issubclass(schema, View):
            raise TypeError(f"{schema.type_name()} is a View")
        self._client = client
        self._schema = schema
        self._ids: list[int] = []
        self._predicates: list[Predicate] = []

    def where(self, *preds: Predicate) -> DeleteBuilder:
        self._predicates.extend(preds)
        return self

    def one(self, id: int) -> DeleteBuilder:
        self._ids = [id]
        return self

    def execute(self) -> int:
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
        mutation = chain_hooks(self._client._hooks, mutation)
        from entpy.active.context import get_effective_ctx

        eval_mutation(get_effective_ctx(self._client), self._client._policies, mutation)
        with self._client._driver.session() as session:
            if _is_gremlin(self._client):
                from entpy.dialect.gremlin import graph_ops

                preds = list(self._predicates) if not self._ids else []
                spec = DeleteSpec(table=label, ids=self._ids, predicates=preds)
                count = graph_ops.delete_nodes(session.g, self._client._registry, spec)
            else:
                table = self._client._registry.table_for(self._schema)
                sql_preds = [p.apply(table) for p in self._predicates] if not self._ids else []
                spec = DeleteSpec(table=table.name, ids=self._ids, predicates=sql_preds)
                count = sqlgraph.delete_nodes(session, self._client._registry.tables, spec)
        if count > 0:
            notify_after_observers(self._client._observers, mutation)
        return count
