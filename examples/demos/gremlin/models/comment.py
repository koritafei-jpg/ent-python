"""Comment 顶点。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field


class Comment(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("text"),
            field.uuid("post_id"),
        ]
