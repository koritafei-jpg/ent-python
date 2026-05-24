"""Section 子表实体（语义 demo）。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field


class Section(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.uuid("document_id"),
            field.string("heading"),
            field.text("content"),
        ]
