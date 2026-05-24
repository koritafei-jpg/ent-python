"""Author 实体。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field


class Author(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("name"),
            field.string("region"),
        ]
