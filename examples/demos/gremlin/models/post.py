"""Post 顶点。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field


class Post(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("title"),
            field.string("topic"),
            field.uuid("author_id"),
        ]
