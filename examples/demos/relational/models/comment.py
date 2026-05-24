"""Comment 实体。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field


class Comment(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("body"),
            field.int_("rating").default(5),
            field.uuid("article_id"),
        ]
