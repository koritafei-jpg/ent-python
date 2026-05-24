"""User 实体。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, edge, field
from entpy.schema import from_, to


class User(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.int_("age").positive(),
            field.string("name").default("unknown"),
        ]

    @classmethod
    def edges(cls):
        from examples.start.models.car import Car
        from examples.start.models.group import Group

        return [
            to("cars", Car),
            from_("groups", Group).ref("users"),
        ]
