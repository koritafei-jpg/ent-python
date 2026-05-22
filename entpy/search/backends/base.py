"""BM25 后端协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ScoredHit:
    id: Any
    score: float
    source: str
    text: str | None = None


class BM25Backend(Protocol):
    """全文 / BM25 检索后端。"""

    name: str

    def search(
        self,
        session,
        table,
        text_column: str,
        query: str,
        *,
        top_k: int = 20,
    ) -> list[ScoredHit]: ...
