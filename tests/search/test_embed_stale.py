"""embed_on_save 清空文本后向量处理。"""

from entpy.runtime import Client
from entpy.runtime.hooks.embed_on_save import embed_on_save_hook
from entpy.search import MockEmbedder
from examples.rag.models import Chunk, SCHEMAS


def test_embed_clears_vector_when_text_cleared():
    emb = MockEmbedder(dim=4)
    client = Client.open_with(
        "sqlite:///:memory:",
        schemas=SCHEMAS,
        hooks=[embed_on_save_hook(emb)],
    )
    client.migrate()
    row = client.create(Chunk, path="/a", nchunk=0, data="hello").save()
    assert row.embedding is not None
    updated = client.update(Chunk, row.id).set("data", "").save()
    assert updated.embedding == [0.0] * 8
    assert updated.embedding != row.embedding
