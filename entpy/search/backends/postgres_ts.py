"""PostgreSQL tsvector 全文后端（开发回退，非真 BM25）。"""

from __future__ import annotations

from entpy.search.backends.base import ScoredHit


class PostgresTSBackend:
    """关键词检索：PG 用 ts_rank，SQLite 用 LIKE。"""

    name = "postgres_ts"

    def search(
        self,
        session,
        table,
        text_column: str,
        query: str,
        *,
        top_k: int = 20,
    ) -> list[ScoredHit]:
        from sqlalchemy import select, func

        col = getattr(table.c, text_column)
        dialect = session.bind.dialect.name

        if dialect == "postgresql":
            ts_query = func.plainto_tsquery("english", query)
            ts_vec = func.to_tsvector("english", col)
            rank = func.ts_rank(ts_vec, ts_query)
            stmt = (
                select(table.c.id, col, rank.label("score"))
                .where(ts_vec.op("@@")(ts_query))
                .order_by(rank.desc())
                .limit(top_k)
            )
            rows = session.execute(stmt).all()
            return [
                ScoredHit(id=r[0], score=float(r[2] or 0), source="bm25", text=r[1])
                for r in rows
            ]

        stmt = select(table.c.id, col).where(col.like(f"%{query}%")).limit(top_k)
        rows = session.execute(stmt).all()
        return [ScoredHit(id=r[0], score=1.0, source="bm25", text=r[1]) for r in rows]
