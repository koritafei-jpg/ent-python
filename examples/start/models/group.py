"""Group 实体。"""

from __future__ import annotations

import re

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, edge, field
from entpy.schema import to

_NAME_RE = re.compile(r"[a-zA-Z_]+$")


class Group(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("name").match(_NAME_RE),
        ]

    @classmethod
    def edges(cls):
        from examples.start.models.user import User

        return [
            to("users", User),
        ]
