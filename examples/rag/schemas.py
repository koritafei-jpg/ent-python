"""RAG 分块 Schema — 对齐 ent RAG + pgvector 教程。"""

from __future__ import annotations

from entpy.schema import Schema, SearchMixin, edge, field
from entpy.schema.search import FullText, Hybrid, SearchConfig, VectorIndex


class Chunk(SearchMixin, Schema):
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


SCHEMAS = [Chunk]
