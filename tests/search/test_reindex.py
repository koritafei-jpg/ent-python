"""检索 reindex CLI 与库函数。"""

from __future__ import annotations

from typer.testing import CliRunner

from entpy.cli.main import app
from entpy.runtime import Client
from entpy.search import MockEmbedder
from entpy.search.reindex import reindex_async, reindex_sync
from examples.rag.schemas import Chunk, SCHEMAS


def _stub_vec():
    return [0.0] * 8


def test_reindex_sync_updates_vectors():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    client.create(
        Chunk, path="/a", nchunk=0, data="alpha", embedding=_stub_vec()
    ).save()
    client.create(
        Chunk, path="/b", nchunk=1, data="beta", embedding=_stub_vec()
    ).save()
    before = client.query(Chunk).all()[0].embedding
    emb = MockEmbedder(dim=8)
    n = reindex_sync(client, Chunk, emb)
    assert n == 2
    after = client.query(Chunk).where(client.F(Chunk).path.eq("/a")).only()
    assert after.embedding != before


def test_reindex_dry_run():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    stub = _stub_vec()
    client.create(Chunk, path="/a", nchunk=0, data="x", embedding=stub).save()
    n = reindex_sync(client, Chunk, MockEmbedder(8), dry_run=True)
    assert n == 1
    row = client.query(Chunk).only()
    assert row.embedding == stub


async def test_reindex_async():
    from entpy.runtime import AsyncClient

    client = AsyncClient.open("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS)
    await client.migrate()
    await client.create(
        Chunk, path="/a", nchunk=0, data="async text", embedding=_stub_vec()
    ).save()
    n = await reindex_async(client, Chunk, MockEmbedder(8))
    assert n == 1
    row = await client.query(Chunk).only()
    assert row.embedding is not None


def test_cli_search_reindex():
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "search",
            "reindex",
            "examples.rag.schemas",
            "--schema",
            "Chunk",
            "--dsn",
            "sqlite:///:memory:",
            "--embedder",
            "mock",
            "--dim",
            "8",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "reindexed" in result.output
