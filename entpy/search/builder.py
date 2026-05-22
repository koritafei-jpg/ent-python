"""SearchBuilder — BM25、语义与混合检索。"""

from __future__ import annotations

from typing import Any

from entpy.schema.base import Schema
from entpy.search.backends.registry import get_bm25_backend
from entpy.search.embedder import Embedder
from entpy.search.hybrid import reciprocal_rank_fusion
from entpy.search.registry import SearchRegistry
from entpy.search.semantic import SemanticBackend


class SearchBuilder:
    def __init__(
        self,
        client: Any,
        schema: type[Schema],
        search_registry: SearchRegistry,
        *,
        bm25_backend: Any = None,
    ) -> None:
        self._client = client
        self._schema = schema
        self._sr = search_registry
        self._bm25_override = bm25_backend
        if not search_registry.has(schema):
            raise ValueError(f"{schema.type_name()} has no search_config")
        self._meta = search_registry.get(schema)

    def _bm25_backend(self):
        if self._bm25_override is not None:
            return self._bm25_override
        name = self._meta.config.bm25_backend
        if self._meta.config.hybrid:
            name = self._meta.config.hybrid.bm25_backend
        return get_bm25_backend(name)

    async def bm25(self, query: str, *, top_k: int = 20) -> list:
        return self.bm25_sync(query, top_k=top_k)

    def bm25_sync(self, query: str, *, top_k: int = 20) -> list:
        if not self._meta.text_columns:
            raise ValueError("no searchable text fields")
        table = self._client._registry.table_for(self._schema)
        col = self._meta.text_columns[0]
        backend = self._bm25_backend()
        with self._client._driver.session() as session:
            return backend.search(session, table, col, query, top_k=top_k)

    async def semantic(
        self,
        query: str | list[float],
        *,
        embedder: Embedder | None = None,
        top_k: int = 20,
    ) -> list:
        return self.semantic_sync(query, embedder=embedder, top_k=top_k)

    def semantic_sync(
        self,
        query: str | list[float],
        *,
        embedder: Embedder | None = None,
        top_k: int = 20,
    ) -> list:
        if not self._meta.vector_column:
            raise ValueError("no vector_field in search_config")
        table = self._client._registry.table_for(self._schema)
        sem = SemanticBackend()
        text_col = self._meta.text_columns[0] if self._meta.text_columns else "data"
        with self._client._driver.session() as session:
            return sem.search(
                session,
                table,
                self._meta.vector_column,
                query,
                embedder,
                top_k=top_k,
                text_column=text_col,
            )

    async def hybrid(
        self,
        query: str,
        *,
        embedder: Embedder,
        top_k: int = 10,
        rrf_k: int | None = None,
    ) -> list:
        return self.hybrid_sync(query, embedder=embedder, top_k=top_k, rrf_k=rrf_k)

    def hybrid_sync(
        self,
        query: str,
        *,
        embedder: Embedder,
        top_k: int = 10,
        rrf_k: int | None = None,
    ) -> list:
        k = rrf_k or (self._meta.config.hybrid.rrf_k if self._meta.config.hybrid else 60)
        bm25_hits = self.bm25_sync(query, top_k=top_k * 2)
        sem_hits = self.semantic_sync(query, embedder=embedder, top_k=top_k * 2)
        return reciprocal_rank_fusion(bm25_hits, sem_hits, k=k)[:top_k]
