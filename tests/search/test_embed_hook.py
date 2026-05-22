"""embed_on_save 钩子。"""

from entpy.runtime import Client
from entpy.runtime.hooks.embed_on_save import embed_on_save_hook
from entpy.search import MockEmbedder
from examples.rag.schemas import Chunk, SCHEMAS


def test_embed_on_save_populates_vector():
    emb = MockEmbedder(dim=8)
    client = Client.open_with(
        "sqlite:///:memory:",
        schemas=SCHEMAS,
        hooks=[embed_on_save_hook(emb)],
    )
    client.migrate()
    row = client.create(Chunk, path="/x", nchunk=0, data="hello world").save()
    assert row.embedding is not None
