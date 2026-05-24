"""ActiveSchema.query() 返回的查询集。"""

from __future__ import annotations

from typing import Any

from entpy.active.entity import ActiveEntity
from entpy.runtime.predicate import Predicate
from entpy.schema.base import Schema


class ActiveQuerySet:
    def __init__(
        self,
        schema: type[Schema],
        client: Any,
        *,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._schema = schema
        self._client = client
        self._builder = client.query(schema)
        for key, value in (kwargs or {}).items():
            self._builder = self._builder.where(_kw_to_predicate(client, schema, key, value))

    def where(self, *preds: Predicate) -> ActiveQuerySet:
        self._builder = self._builder.where(*preds)
        return self

    def entql(self, filter_obj: dict) -> ActiveQuerySet:
        self._builder = self._builder.entql(filter_obj)
        return self

    def with_(self, *edges: str) -> ActiveQuerySet:
        self._builder = self._builder.with_(*edges)
        return self

    def limit(self, n: int) -> ActiveQuerySet:
        self._builder = self._builder.limit(n)
        return self

    def all(self) -> list[ActiveEntity]:
        return [ActiveEntity.from_entity(e) for e in self._builder.all()]

    def first(self) -> ActiveEntity | None:
        row = self._builder.first()
        return ActiveEntity.from_entity(row) if row else None

    def only(self) -> ActiveEntity:
        return ActiveEntity.from_entity(self._builder.only())


def _kw_to_predicate(client: Any, schema: type[Schema], key: str, value: Any) -> Predicate:
    try:
        field_ref = getattr(client.F(schema), key)
    except AttributeError as exc:
        raise ValueError(str(exc)) from exc
    return field_ref.eq(value)
