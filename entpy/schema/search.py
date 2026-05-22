"""BM25 与语义检索配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FullText:
    weight: float = 1.0
    language: str = "english"
    backend: str | None = None


@dataclass
class VectorIndex:
    hnsw: bool = True
    op_class: str = "vector_cosine_ops"
    m: int = 16
    ef_construction: int = 64


@dataclass
class Hybrid:
    bm25_backend: str = "postgres_ts"
    rrf_k: int = 60
    top_k: int = 20


@dataclass
class SearchConfig:
    text_fields: list[str]
    vector_field: str | None = None
    vector_edge: str | None = None
    hybrid: Hybrid | None = None
    bm25_backend: str = "postgres_ts"
