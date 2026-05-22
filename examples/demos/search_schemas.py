"""可检索 Document + Section（子表 FK）。"""

from __future__ import annotations

from entpy.active import ActiveSchema
from entpy.schema import Schema, SearchMixin, field
from entpy.schema.search import FullText, Hybrid, SearchConfig


class Document(SearchMixin, ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.string("title"),
            field.string("category"),
            field.string("lang").default("en"),
            field.text("content").searchable(FullText(language="english")),
            field.vector("embedding", dimensions=8),
        ]

    @classmethod
    def search_config(cls) -> SearchConfig:
        return SearchConfig(
            text_fields=["content"],
            vector_field="embedding",
            hybrid=Hybrid(bm25_backend="postgres_ts", rrf_k=60, top_k=10),
        )


class Section(ActiveSchema, Schema):
    @classmethod
    def fields(cls):
        return [
            field.int_("document_id"),
            field.string("heading"),
            field.text("content"),
        ]


SEARCH_SCHEMAS = [Document, Section]
