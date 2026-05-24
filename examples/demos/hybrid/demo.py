#!/usr/bin/env python3
"""演示 4：BM25 + 语义混合检索（RRF）— 基础查询、加条件、复杂查询、子表。"""

from __future__ import annotations

from entpy.active import bind, migrate, search
from examples.demos.hybrid.models import Document, Section, SEARCH_SCHEMAS
from examples.demos.hybrid.seed import seed
from examples.demos.common.print_observers import print_observer_events
from examples.demos.common.search_helpers import filter_hits


def main() -> None:
    print("演示 4 — 混合检索")
    with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
        migrate()
        emb = seed()
        sb = search(Document)

        print("\n=== 1. 混合检索基础 ===")
        hits = sb.hybrid_sync("pgvector entpy runtime", embedder=emb, top_k=5)
        for h in hits:
            print(f"  id={h.id} score={h.score:.3f} source={h.source}")

        print("\n=== 2. 混合 + 条件 ===")
        raw = sb.hybrid_sync("graph database search", embedder=emb, top_k=10)
        for h in filter_hits(Document, raw, category="tech", lang="en"):
            print(f"  id={h.id} score={h.score:.3f}")

        print("\n=== 3. 复杂查询 (混合 + 条件 + 业务排序) ===")
        raw = sb.hybrid_sync("vector ORM", embedder=emb, top_k=12, rrf_k=60)
        filtered = filter_hits(Document, raw, category="tech")
        top5 = sorted(filtered, key=lambda h: h.score, reverse=True)[:5]
        titles = [Document.get(id=h.id).title for h in top5]
        print(f"  titles: {titles}")

        print("\n=== 4. 子表 ===")
        for h in sb.hybrid_sync("entpy", embedder=emb, top_k=3):
            doc = Document.get(id=h.id)
            n = len(Section.query(document_id=doc.id).all())
            print(f"  [{doc.id}] {doc.title} -> {n} section(s)")
            print(f"    create_time={doc.create_time}")

        print_observer_events()


if __name__ == "__main__":
    main()
