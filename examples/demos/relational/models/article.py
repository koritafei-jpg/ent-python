"""Article 实体。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field


class Article(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("title"),
            field.string("body"),
            field.string("status").default("draft"),
            field.uuid("author_id"),
        ]
