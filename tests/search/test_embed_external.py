"""外部 Embedding API 接入 embed_on_save_hook。"""

from __future__ import annotations

import asyncio

import pytest

from entpy.active import async_bind, bind, migrate, migrate_async
from entpy.active.context import get_async_client, get_client
from entpy.runtime import Client
from entpy.runtime.hook import AsyncHook, Hook
from entpy.runtime.hooks import embed_on_save_hook
from entpy.search import callable_embedder
from examples.rag.models import Chunk, SCHEMAS


def test_embed_on_save_callable_sync():
    calls: list[list[str]] = []

    def external_api(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[float(len(t)), 1.0] for t in texts]

    with bind(
        "sqlite:///:memory:",
        schemas=SCHEMAS,
        hooks=[embed_on_save_hook(external_api)],
    ):
        migrate()
        row = get_client().create(
            Chunk, path="/ext", nchunk=0, data="hello external"
        ).save()
        assert row.embedding == [14.0, 1.0]
        assert calls == [["hello external"]]


def test_embed_on_save_callable_embedder_helper():
    with bind(
        "sqlite:///:memory:",
        schemas=SCHEMAS,
        hooks=[
            embed_on_save_hook(
                callable_embedder(
                    embed_sync=lambda texts: [[1.0, 2.0] for _ in texts]
                )
            )
        ],
    ):
        migrate()
        row = get_client().create(Chunk, path="/h", nchunk=0, data="x").save()
        assert row.embedding == [1.0, 2.0]


def test_embed_on_save_async_only_client():
    class AsyncOnlyAPI:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.5] * 4 for _ in texts]

    hook = embed_on_save_hook(AsyncOnlyAPI())
    assert isinstance(hook, AsyncHook)

    async def run():
        async with async_bind(
            "sqlite+aiosqlite:///:memory:",
            schemas=SCHEMAS,
            hooks=[hook],
        ):
            await migrate_async()
            row = await get_async_client().create(
                Chunk, path="/a", nchunk=0, data="async api"
            ).save()
            assert len(row.embedding) == 4

    asyncio.run(run())


def test_mock_embedder_defaults_to_sync_hook():
    from entpy.search import MockEmbedder

    hook = embed_on_save_hook(MockEmbedder(4))
    assert isinstance(hook, Hook)


def test_open_with_external_class():
    class HttpEmbedClient:
        def embed_sync(self, texts: list[str]) -> list[list[float]]:
            return [[3.0, 3.0] for _ in texts]

    client = Client.open_with(
        "sqlite:///:memory:",
        schemas=SCHEMAS,
        hooks=[embed_on_save_hook(HttpEmbedClient())],
    )
    client.migrate()
    row = client.create(Chunk, path="/c", nchunk=0, data="z").save()
    assert row.embedding == [3.0, 3.0]
