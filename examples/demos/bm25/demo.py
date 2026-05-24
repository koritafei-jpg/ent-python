#!/usr/bin/env python3
"""演示 2：BM25 全文检索 — 基础查询、加条件、复杂查询、子表。"""

from __future__ import annotations

from entpy.active import migrate, search
from examples.demos.bm25.models import Document, Section, SEARCH_SCHEMAS
from examples.demos.bm25.seed import seed
from examples.demos.common.connect import demo_bind
from examples.demos.common.search_helpers import filter_hits
from examples.demos.common.print_observers import print_observer_events


def main() -> None:
    print("演示 2 — BM25 全文检索")
    with demo_bind(SEARCH_SCHEMAS):
        migrate()
        seed()
        sb = search(Document)

        print("\n=== 1. BM25 基础查询 ===")
        hits = sb.bm25_sync("entpy runtime", top_k=5)
        for h in hits:
            print(f"  id={h.id} score={h.score:.3f} text={h.text!r}")

        print("\n=== 2. BM25 + 条件 (category=tech) ===")
        raw = sb.bm25_sync("entpy runtime graph", top_k=10)
        for h in filter_hits(Document, raw, category="tech", lang="en"):
            print(f"  id={h.id} score={h.score:.3f}")

        print("\n=== 3. 复杂查询 (BM25 后多条件) ===")
        raw = sb.bm25_sync("search", top_k=10)
        filtered = filter_hits(Document, raw, category="tech")
        filtered = [h for h in filtered if h.score >= 0.5]
        print(f"  tech + score>=0.5: {len(filtered)} hit(s)")

        print("\n=== 4. 子表 — 按 document_id 查 Section ===")
        for h in sb.bm25_sync("pgvector", top_k=3):
            doc = Document.get(id=h.id)
            n = len(Section.query(document_id=doc.id).all())
            print(f"  [{doc.id}] {doc.title} -> {n} section(s)")

        print("\n=== 5. 子表复杂条件 ===")
        doc = Document.get(title="entpy SQL runtime")
        for s in Section.query(document_id=doc.id).all():
            print(f"  section id={s.id} heading={s.heading}")

        print("\n=== 6. BaseSchema 时间戳 ===")
        print(f"  doc create_time={doc.create_time} delete_time={doc.delete_time}")

        print_observer_events()


if __name__ == "__main__":
    main()
