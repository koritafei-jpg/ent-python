"""Client.scope / transaction / lifecycle 与 async 遍历。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from entpy.active import async_bind, bind, migrate, migrate_async
from entpy.active.context import get_async_client, get_client
from entpy.runtime import Client
from examples.start.models import Group, User, SCHEMAS


def test_client_scope_without_dispose():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        with client.scope():
            client.migrate()
            u = client.create(User, name="scoped", age=1).save()
            assert u.name == "scoped"
        with client.scope():
            found = client.query(User).where(client.F(User).name.eq("scoped")).only()
            assert found.id == u.id
    finally:
        client.close()


def test_bind_app_lifecycle_keeps_engine():
    client_holder: list[Client] = []

    with bind("sqlite:///:memory:", schemas=SCHEMAS, lifecycle="app") as client:
        client_holder.append(client)
        migrate()
        User.create(name="app", age=1)

    c = client_holder[0]
    with c.scope():
        assert User.query(name="app").first() is not None
    c.close()


def test_transaction_atomic_commit():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        with client.transaction():
            client.create(User, name="in_tx", age=1).save()
            client.create(User, name="in_tx2", age=2).save()
        assert client.query(User).where(client.F(User).name.eq("in_tx")).first() is not None
        assert client.query(User).where(client.F(User).name.eq("in_tx2")).first() is not None


def test_transaction_rollback():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        with pytest.raises(ValueError):
            with client.transaction():
                client.create(User, name="rollback_me", age=1).save()
                raise ValueError("abort")
        assert (
            client.query(User).where(client.F(User).name.eq("rollback_me")).first()
            is None
        )


def test_async_entity_out():
    async def run():
        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            await migrate_async()
            client = get_async_client()
            u = await client.create(User, name="U", age=1).save()
            g = await client.create(Group, name="g_valid").save()
            await client.update(User, u.id).add("groups", g.id).save()
            loaded = await u.out("groups").all()
            assert len(loaded) == 1
            assert loaded[0].name == "g_valid"

    asyncio.run(run())


def test_async_transaction():
    async def run():
        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            await migrate_async()
            client = get_async_client()
            async with client.transaction():
                await client.create(User, name="async_tx", age=1).save()
            found = await client.query(User).where(
                client.F(User).name.eq("async_tx")
            ).only()
            assert found.name == "async_tx"

    asyncio.run(run())
