"""BM25 后端。"""

from entpy.runtime import Client
from entpy.search.backends.opensearch import MockOpenSearchBackend
from entpy.search.builder import SearchBuilder
from entpy.search.registry import SearchRegistry
from examples.rag.models import Chunk, SCHEMAS


def test_mock_opensearch_backend():
    docs = [
        {"id": 1, "data": "database migration guide"},
        {"id": 2, "data": "cooking pasta"},
    ]
    backend = MockOpenSearchBackend(documents=docs)
    hits = backend.search(None, None, "data", "migration", top_k=5)
    assert len(hits) == 1
    assert hits[0].id == 1


def test_search_builder_mock_bm25():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    emb = __import__("entpy.search", fromlist=["MockEmbedder"]).MockEmbedder(8)
    client.create(
        Chunk,
        path="/a",
        nchunk=0,
        data="database migration",
        embedding=emb.embed_sync(["x"])[0],
    ).save()

    sr = SearchRegistry.from_registry(client._registry)
    mock = MockOpenSearchBackend(
        documents=[{"id": 1, "data": "database migration"}],
    )
    sb = SearchBuilder(client, Chunk, sr, bm25_backend=mock)
    hits = sb.bm25_sync("migration", top_k=5)
    assert hits[0].source == "bm25"
