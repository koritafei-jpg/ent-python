"""SearchRegistry 元数据。"""

from entpy.runtime.registry import Registry
from entpy.search.registry import SearchRegistry
from examples.rag.models import Chunk, SCHEMAS as RAG_SCHEMAS


def test_search_registry_chunk():
    reg = Registry.from_schemas(RAG_SCHEMAS)
    sr = SearchRegistry.from_registry(reg)
    assert sr.has(Chunk)
    meta = sr.get(Chunk)
    assert "data" in meta.text_columns or meta.text_columns
    assert meta.vector_column == "embedding"
    assert meta.config.hybrid is not None
    assert meta.config.hybrid.bm25_backend == "postgres_ts"
