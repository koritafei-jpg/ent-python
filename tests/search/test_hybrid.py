from entpy.runtime import Client
from entpy.search import MockEmbedder
from entpy.search.backends.base import ScoredHit  # noqa: F401
from examples.rag.schemas import Chunk, SCHEMAS


def test_chunk_hybrid_search():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()

    emb = MockEmbedder(dim=8)
    client.create(
        Chunk,
        path="/doc1",
        nchunk=0,
        data="database migration with ent",
        embedding=emb.embed_sync(["database migration"])[0],
    ).save()
    client.create(
        Chunk,
        path="/doc2",
        nchunk=0,
        data="unrelated cooking recipe",
        embedding=emb.embed_sync(["cooking recipe"])[0],
    ).save()

    hits = client.search(Chunk).hybrid_sync(
        "database migration",
        embedder=emb,
        top_k=5,
    )
    assert len(hits) >= 1
    assert hits[0].id == 1
