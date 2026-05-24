"""性能与健壮性相关回归测试。"""

from __future__ import annotations

import asyncio

import pytest

from entpy.active import async_bind, bind, migrate, migrate_async
from entpy.active.context import get_async_client, get_client, get_effective_ctx
from entpy.runtime import Client
from examples.start.models import User, SCHEMAS


def test_unknown_edge_raises():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        with pytest.raises(ValueError, match="unknown edge"):
            get_client().create(User, name="x", age=1).add("not_an_edge", 1).save()


def test_delete_by_predicate_without_load():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        client.create(User, name="keep", age=1).save()
        client.create(User, name="drop", age=2).save()
        count = (
            client.delete(User)
            .where(client.F(User).name.eq("drop"))
            .execute()
        )
        assert count == 1
        assert client.query(User).where(client.F(User).name.eq("drop")).first() is None
        assert client.query(User).where(client.F(User).name.eq("keep")).first() is not None


def test_scope_ctx_overlay_concurrent_safe():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        with client.scope(ctx={"tenant": "a"}):
            assert get_effective_ctx(client)["tenant"] == "a"
        with client.scope(ctx={"tenant": "b"}):
            assert get_effective_ctx(client)["tenant"] == "b"
    finally:
        client.close()


def test_async_hooks_do_not_block_event_loop():
    async def run():
        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            await migrate_async()
            client = get_async_client()
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            await client.create(User, name="fast", age=1).save()
            elapsed = loop.time() - t0
            assert elapsed < 1.0

    asyncio.run(run())
