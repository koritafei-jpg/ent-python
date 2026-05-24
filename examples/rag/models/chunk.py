"""RAG 分块实体。"""

from __future__ import annotations

from entpy.schema import BaseSchema, SearchMixin, field
from entpy.schema.search import FullText, Hybrid, SearchConfig


class Chunk(SearchMixin, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("path"),
            field.int_("nchunk"),
            field.text("data").searchable(FullText(language="english")),
            field.vector("embedding", dimensions=8),
        ]

    @classmethod
    def search_config(cls) -> SearchConfig:
        return SearchConfig(
            text_fields=["data"],
            vector_field="embedding",
            hybrid=Hybrid(bm25_backend="postgres_ts", rrf_k=60, top_k=10),
        )
