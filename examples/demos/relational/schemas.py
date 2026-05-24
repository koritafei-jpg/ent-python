"""CRM 关系模型 — BaseSchema + UUID FK（author_id / article_id）。"""

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


class Article(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("title"),
            field.string("body"),
            field.string("status").default("draft"),
            field.uuid("author_id"),
        ]


class Comment(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("body"),
            field.int_("rating").default(5),
            field.uuid("article_id"),
        ]


SCHEMAS = [Author, Article, Comment]
