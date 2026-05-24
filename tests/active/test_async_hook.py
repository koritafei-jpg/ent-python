"""原生 AsyncHook 与 SQL 多跳 fast path。"""

from __future__ import annotations

import asyncio

import pytest

from entpy.active import async_bind, bind, migrate, migrate_async
from entpy.active.context import get_async_client, get_client
from entpy.runtime import Client
from entpy.runtime.hook import AsyncHook, chain_hooks_async
from entpy.runtime.hooks.embed_on_save import embed_on_save_async_hook, embed_on_save_hook
from entpy.runtime.mutation import Mutation, Op
from entpy.search import MockEmbedder
from examples.demos.gremlin.models import Person, GREMLIN_SCHEMAS
from examples.start.models import User, SCHEMAS


def test_sql_traverse_chain_join_fast_path():
    client = Client.open("sqlite:///:memory:", schemas=GREMLIN_SCHEMAS)
    try:
        client.migrate()
        alice = client.create(Person, name="Alice", city="NYC").save()
        bob = client.create(Person, name="Bob", city="SF").save()
        carol = client.create(Person, name="Carol", city="NYC").save()
        client.update(Person, alice.id).add("knows", bob.id).save()
        client.update(Person, bob.id).add("knows", carol.id).save()
        fof = alice.out("knows").out("knows").all()
        assert len(fof) == 1
        assert fof[0].name == "Carol"
    finally:
        client.close()


def test_update_save_returns_row_without_reload():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="orig", age=1)
        u.name = "updated"
        u.save()
        assert u.name == "updated"
        refetched = User.get(id=u.id)
        assert refetched.name == "updated"


@pytest.mark.asyncio
async def test_async_hook_native_chain():
    calls: list[str] = []

    @AsyncHook
    async def first(next_mutator, mutation: Mutation):
        calls.append("first")
        return await next_mutator.mutate(mutation)

    @AsyncHook
    async def second(next_mutator, mutation: Mutation):
        calls.append("second")
        result = await next_mutator.mutate(mutation)
        calls.append("done")
        return result

    m = Mutation(User, Op.CREATE, fields={"name": "x"})
    await chain_hooks_async([first, second], m)
    assert calls == ["first", "second", "done"]


def test_embed_async_hook_uses_native_embed():
    async def run():
        from examples.rag.models import Chunk, SCHEMAS as RAG_SCHEMAS

        emb = MockEmbedder(dim=4)
        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=RAG_SCHEMAS):
            await migrate_async()
            client = get_async_client()
            client._hooks = [embed_on_save_async_hook(emb)]
            row = await client.create(Chunk, path="/a", nchunk=0, data="hello").save()
            assert row.embedding is not None

    asyncio.run(run())


def test_sync_client_rejects_async_hook_in_chain():
    with pytest.raises(TypeError, match="AsyncHook cannot run in sync"):
        from entpy.runtime.hook import chain_hooks

        @AsyncHook
        async def h(next_m, m):
            return await next_m.mutate(m)

        chain_hooks([h], Mutation(User, Op.CREATE, fields={}))
