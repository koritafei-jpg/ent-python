"""Person 顶点。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, edge, field
from entpy.schema import to


class Person(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("name"),
            field.string("city"),
        ]

    @classmethod
    def edges(cls):
        from examples.demos.gremlin.models.person import Person

        return [to("knows", Person)]
