"""CRM 关系模型 — 显式 FK 字段（便于子表查询）。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import Schema, field


class Author(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.string("name"),
            field.string("region"),
        ]


class Article(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.string("title"),
            field.string("body"),
            field.string("status").default("draft"),
            field.int_("author_id"),
        ]


class Comment(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.string("body"),
            field.int_("rating").default(5),
            field.int_("article_id"),
        ]


SCHEMAS = [Author, Article, Comment]
