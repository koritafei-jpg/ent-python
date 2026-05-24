"""语义检索：SQLite 暴力回退与可选 pgvector 集成。"""

import os

import pytest

from entpy.runtime import Client
from entpy.search import MockEmbedder
from examples.rag.models import Chunk, SCHEMAS


def test_semantic_sqlite_brute():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    emb = MockEmbedder(dim=8)
    client.create(
        Chunk,
        path="/a",
        nchunk=0,
        data="cats and dogs",
        embedding=emb.embed_sync(["cats"])[0],
    ).save()
    db_chunk = client.create(
        Chunk,
        path="/b",
        nchunk=0,
        data="database sql",
        embedding=emb.embed_sync(["database sql"])[0],
    ).save()
    hits = client.search(Chunk).semantic_sync("database", embedder=emb, top_k=2)
    assert hits[0].id == db_chunk.id


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("ENTPY_PGVECTOR_DSN") is None,
    reason="set ENTPY_PGVECTOR_DSN=postgresql+psycopg2://entpy:entpy@localhost:5433/entpy_test",
)
def test_semantic_pgvector_integration():
    pytest.importorskip("pgvector")
    dsn = os.environ["ENTPY_PGVECTOR_DSN"]
    client = Client.open(dsn, schemas=SCHEMAS)
    client.migrate()
    emb = MockEmbedder(dim=8)
    for i, text in enumerate(["apple fruit", "database vector search"], start=1):
        client.create(
            Chunk,
            path=f"/{i}",
            nchunk=0,
            data=text,
            embedding=emb.embed_sync([text])[0],
        ).save()
    hits = client.search(Chunk).semantic_sync("database vector", embedder=emb, top_k=2)
    assert hits[0].id == 2
