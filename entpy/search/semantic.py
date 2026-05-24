"""语义检索：PostgreSQL pgvector；SQLite 仅开发态可显式启用暴力扫描。"""

from __future__ import annotations

import json
import math
from typing import Any

from entpy.search.backends.base import ScoredHit
from entpy.search.embedder import Embedder

# SQLite 等暴力余弦扫描的行数上限（防止 OOM）
SEMANTIC_BRUTE_MAX_ROWS = 10_000


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


def _parse_vector(vec: Any) -> list[float] | None:
    if vec is None:
        return None
    if isinstance(vec, str):
        try:
            vec = json.loads(vec)
        except json.JSONDecodeError:
            return None
    if hasattr(vec, "tolist"):
        return list(vec.tolist())
    if isinstance(vec, (list, tuple)):
        return list(vec)
    return None


class SemanticBackend:
    def search_brute(
        self,
        rows: list[dict],
        vector_column: str,
        query_vec: list[float],
        *,
        top_k: int = 20,
    ) -> list[ScoredHit]:
        scored = []
        for row in rows:
            vec = _parse_vector(row.get(vector_column))
            if vec is None:
                continue
            dist = 1.0 - _cosine(vec, query_vec)
            scored.append((row["id"], dist, row))
        scored.sort(key=lambda x: x[1])
        return [
            ScoredHit(
                id=s[0],
                score=1.0 - s[1],
                source="semantic",
                text=s[2].get("data"),
            )
            for s in scored[:top_k]
        ]

    def search_pgvector(
        self,
        session,
        table,
        vector_column: str,
        query_vec: list[float],
        *,
        top_k: int = 20,
        text_column: str | None = "data",
    ) -> list[ScoredHit]:
        """PostgreSQL 上按 embedding 与查询的余弦距离排序。"""
        from sqlalchemy import select, text

        col = getattr(table.c, vector_column)
        # pgvector SQLAlchemy：余弦距离
        try:
            dist_expr = col.cosine_distance(query_vec)
        except AttributeError:
            # 回退为原始 SQL
            stmt = text(
                f"SELECT id, {text_column}, "
                f"({vector_column} <=> :q) AS dist "
                f"FROM {table.name} "
                f"ORDER BY dist LIMIT :k"
            )
            rows = session.execute(stmt, {"q": str(query_vec), "k": top_k}).mappings().all()
            return [
                ScoredHit(
                    id=r["id"],
                    score=1.0 / (1.0 + float(r["dist"])),
                    source="semantic",
                    text=r.get(text_column),
                )
                for r in rows
            ]

        stmt = (
            select(table.c.id, getattr(table.c, text_column) if text_column else table.c.id, dist_expr.label("dist"))
            .order_by(dist_expr)
            .limit(top_k)
        )
        rows = session.execute(stmt).all()
        return [
            ScoredHit(
                id=r[0],
                score=1.0 / (1.0 + float(r[2])),
                source="semantic",
                text=r[1] if text_column else None,
            )
            for r in rows
        ]

    def search(
        self,
        session,
        table,
        vector_column: str,
        query: str | list[float],
        embedder: Embedder | None,
        *,
        top_k: int = 20,
        text_column: str | None = "data",
        allow_brute_fallback: bool = False,
    ) -> list[ScoredHit]:
        if isinstance(query, str):
            if embedder is None:
                raise ValueError("embedder required for text query")
            query_vec = embedder.embed_sync([query])[0]
        else:
            query_vec = query

        dialect = session.bind.dialect.name
        if dialect == "postgresql":
            try:
                import pgvector  # noqa: F401

                return self.search_pgvector(
                    session,
                    table,
                    vector_column,
                    query_vec,
                    top_k=top_k,
                    text_column=text_column,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "semantic search on PostgreSQL requires pgvector; "
                    "pip install pgvector"
                ) from exc

        if dialect == "sqlite" and allow_brute_fallback:
            return self._search_brute_table(
                session, table, vector_column, query_vec, top_k=top_k
            )

        raise RuntimeError(
            f"semantic search on {dialect!r} requires pgvector (PostgreSQL) "
            "or allow_brute_fallback=True on SQLite for development only"
        )

    def _search_brute_table(
        self,
        session,
        table,
        vector_column: str,
        query_vec: list[float],
        *,
        top_k: int,
    ) -> list[ScoredHit]:
        from sqlalchemy import func, select

        count = session.execute(select(func.count()).select_from(table)).scalar_one()
        if count > SEMANTIC_BRUTE_MAX_ROWS:
            raise RuntimeError(
                f"brute semantic scan refused: {count} rows exceeds "
                f"SEMANTIC_BRUTE_MAX_ROWS={SEMANTIC_BRUTE_MAX_ROWS}"
            )
        rows = session.execute(select(table)).mappings().all()
        data = [dict(r) for r in rows]
        return self.search_brute(data, vector_column, query_vec, top_k=top_k)
