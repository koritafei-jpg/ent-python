"""ent 入门示例 — https://entgo.io/docs/getting-started"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from entpy.active import ActiveSchema
from entpy.schema import Schema, edge, field
from entpy.schema import from_, to

_NAME_RE = re.compile(r"[a-zA-Z_]+$")


class User(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.int_("age").positive(),
            field.string("name").default("unknown"),
        ]

    @classmethod
    def edges(cls):
        return [
            to("cars", Car),
            from_("groups", Group).ref("users"),
        ]


class Car(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.string("model"),
            field.time("registered_at").default(
                lambda: datetime.now(timezone.utc)
            ),
        ]

    @classmethod
    def edges(cls):
        return [
            from_("owner", User).ref("cars").unique(),
        ]


class Group(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.string("name").match(_NAME_RE),
        ]

    @classmethod
    def edges(cls):
        return [
            to("users", User),
        ]


SCHEMAS = [User, Car, Group]
