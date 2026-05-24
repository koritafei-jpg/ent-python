"""BM25 demo 种子数据。"""

from __future__ import annotations

from entpy.search import MockEmbedder
from examples.demos.bm25.models import Document, Section


def seed(*, dim: int = 8) -> MockEmbedder:
    emb = MockEmbedder(dim=dim)
    docs = [
        ("entpy SQL runtime", "tech", "en", "entpy 运行时优先的 ORM，无需代码生成"),
        ("PostgreSQL pgvector", "tech", "en", "vector search with pgvector and HNSW index"),
        ("French cooking", "life", "fr", "recette de cuisine française"),
        ("Graph gremlin", "tech", "en", "TinkerPop gremlin graph traversal multi-hop"),
        ("Draft memo", "tech", "en", "unpublished draft about internal tools"),
    ]
    for title, cat, lang, content in docs:
        vec = emb.embed_sync([content])[0]
        row = Document.create(
            title=title,
            category=cat,
            lang=lang,
            content=content,
            embedding=vec,
        )
        Section.create(
            document_id=row.id,
            heading=f"{title} — summary",
            content=content[:60],
        )
    return emb
