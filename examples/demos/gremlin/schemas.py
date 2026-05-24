"""社交图 — BaseSchema + Person knows 边 + Post/Comment UUID FK。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, edge, field
from entpy.schema import to


class Person(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("name"),
            field.string("city"),
        ]

    @classmethod
    def edges(cls):
        return [to("knows", Person)]


class Post(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("title"),
            field.string("topic"),
            field.uuid("author_id"),
        ]


class Comment(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("text"),
            field.uuid("post_id"),
        ]


GREMLIN_SCHEMAS = [Person, Post, Comment]
