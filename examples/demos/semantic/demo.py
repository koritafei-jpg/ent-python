#!/usr/bin/env python3
"""演示 3：语义（向量）检索 — 基础查询、加条件、复杂查询、子表。"""

from __future__ import annotations

from entpy.active import migrate, search
from examples.demos.semantic.models import Document, Section, SEARCH_SCHEMAS
from examples.demos.semantic.seed import seed
from examples.demos.common.connect import demo_bind
from examples.demos.common.print_observers import print_observer_events
from examples.demos.common.search_helpers import filter_hits


def main() -> None:
    print("演示 3 — 语义检索")
    with demo_bind(SEARCH_SCHEMAS):
        migrate()
        emb = seed()
        sb = search(Document)

        print("\n=== 1. 语义基础查询 ===")
        hits = sb.semantic_sync("vector database embedding", embedder=emb, top_k=5)
        for h in hits:
            print(f"  id={h.id} score={h.score:.3f} text={h.text!r}")

        print("\n=== 2. 语义 + 条件 (lang=en, category=tech) ===")
        raw = sb.semantic_sync("graph traversal", embedder=emb, top_k=10)
        for h in filter_hits(Document, raw, lang="en", category="tech"):
            print(f"  id={h.id} score={h.score:.3f}")

        print("\n=== 3. 复杂查询 (语义 + 多条件 + top 过滤) ===")
        raw = sb.semantic_sync("runtime ORM framework", embedder=emb, top_k=10)
        filtered = filter_hits(Document, raw, category="tech", lang="en")
        top3 = sorted(filtered, key=lambda h: h.score, reverse=True)[:3]
        print(f"  top-3 after filter: {[h.id for h in top3]}")

        print("\n=== 4. 子表 (Section.document_id) ===")
        for h in sb.semantic_sync("pgvector", embedder=emb, top_k=2):
            doc = Document.get(id=h.id)
            n = len(Section.query(document_id=doc.id).all())
            print(f"  doc={doc.title} sections={n}")
            print(f"    create_time={doc.create_time}")

        print("\n=== 5. ActiveEntity save / edit() ===")
        doc = Document.get(title="entpy SQL runtime")
        doc.category = "tech"
        doc.save()
        doc.edit().set("lang", "en").save()

        print_observer_events()


if __name__ == "__main__":
    main()
