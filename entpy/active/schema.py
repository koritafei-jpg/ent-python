"""ActiveSchema 混入类：create / query / get，无需显式 Client。"""

from __future__ import annotations

from typing import Any

from entpy.active.context import get_client
from entpy.active.entity import ActiveEntity
from entpy.active.queryset import ActiveQuerySet
from entpy.schema.base import Schema, View


class ActiveSchema:
    """混入：`class User(ActiveSchema, BaseSchema)`，需在 `with entpy.active.bind(...):` 内使用。"""

    @classmethod
    def create(cls, /, **fields: Any) -> ActiveEntity:
        if issubclass(cls, View):
            raise TypeError(f"{cls.type_name()} is a View")
        client = get_client()
        entity = client.create(cls, **fields).save()
        return ActiveEntity.from_entity(entity)

    @classmethod
    def new(cls, /, **fields: Any) -> ActiveEntity:
        """未持久化实例；调用 .save() 写入。"""
        if issubclass(cls, View):
            raise TypeError(f"{cls.type_name()} is a View")
        return ActiveEntity(cls, dict(fields), get_client(), _new=True)

    @classmethod
    def query(cls, **kwargs: Any) -> ActiveQuerySet:
        return ActiveQuerySet(cls, get_client(), kwargs=kwargs)

    @classmethod
    def get(cls, **kwargs: Any) -> ActiveEntity:
        return ActiveQuerySet(cls, get_client(), kwargs=kwargs).only()
