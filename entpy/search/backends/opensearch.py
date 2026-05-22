"""OpenSearch BM25 后端（可选 opensearch-py）。"""

from __future__ import annotations

from typing import Any

from entpy.search.backends.base import ScoredHit


class OpenSearchBackend:
    """生产环境：OpenSearch match 查询 BM25。"""

    name = "opensearch"

    def __init__(
        self,
        *,
        hosts: list[str] | None = None,
        index: str | None = None,
        text_field: str = "data",
        client: Any = None,
    ) -> None:
        self._hosts = hosts or ["http://localhost:9200"]
        self._index = index
        self._text_field = text_field
        self._client = client

    def _client_or_create(self, index: str):
        if self._client is not None:
            return self._client
        try:
            from opensearchpy import OpenSearch
        except ImportError as e:
            raise ImportError("pip install opensearch-py") from e
        return OpenSearch(hosts=self._hosts)

    def search(
        self,
        session,
        table,
        text_column: str,
        query: str,
        *,
        top_k: int = 20,
    ) -> list[ScoredHit]:
        index = self._index or table.name
        client = self._client_or_create(index)
        body = {
            "query": {"match": {text_column: {"query": query}}},
            "size": top_k,
        }
        res = client.search(index=index, body=body)
        hits = []
        for h in res.get("hits", {}).get("hits", []):
            doc_id = h.get("_id")
            score = float(h.get("_score", 0.0))
            src = h.get("_source", {})
            text = src.get(text_column)
            hits.append(ScoredHit(id=doc_id, score=score, source="bm25", text=text))
        return hits


class MockOpenSearchBackend:
    """内存 BM25 类排序（测试用，无需 OpenSearch）。"""

    name = "opensearch"

    def __init__(self, *, documents: list[dict] | None = None) -> None:
        self._docs = documents or []

    def search(
        self,
        session,
        table,
        text_column: str,
        query: str,
        *,
        top_k: int = 20,
    ) -> list[ScoredHit]:
        q = query.lower()
        scored = []
        for doc in self._docs:
            text = str(doc.get(text_column, "")).lower()
            if q not in text:
                continue
            score = text.count(q) + (10 if text.startswith(q) else 0)
            scored.append(
                ScoredHit(id=doc["id"], score=float(score), source="bm25", text=doc.get(text_column))
            )
        scored.sort(key=lambda x: -x.score)
        return scored[:top_k]
