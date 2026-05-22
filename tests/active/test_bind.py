"""bind 与 ActiveSchema.create / query / save。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from entpy.active import async_bind, bind, migrate, migrate_async, get_async_client, F
from examples.start.schemas import User, Car, SCHEMAS


def test_bind_create_query():
    with bind("sqlite:///:memory:", schemas=SCHEMAS) as client:
        migrate()
        alice = User.create(name="Alice", age=30)
        assert alice.id is not None
        found = User.query(name="Alice").only()
        assert found.age == 30
        assert client is not None


def test_bind_new_save_update():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.new(name="Bob", age=25)
        u.save()
        assert u.id is not None
        u.age = 26
        u.save()
        refetched = User.get(id=u.id)
        assert refetched.age == 26


def test_bind_query_with_edges():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="T", age=1)
        c = Car.create(model="X", registered_at=datetime.now(timezone.utc))
        from entpy.active.context import get_client

        get_client().update(User, u.id).add("cars", c.id).save()
        loaded = User.query(id=u.id).with_("cars").only()
        assert len(loaded._edges.get("cars", [])) == 1


def test_bind_delete():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="del", age=1)
        u.delete()
        assert User.query(name="del").first() is None


def test_outside_bind_raises():
    with pytest.raises(RuntimeError, match="no active entpy bind"):
        User.create(name="x")


async def test_async_bind():
    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        client = get_async_client()
        u = await client.create(User, name="async_u", age=5).save()
        found = await client.query(User).where(
            client.F(User).name.eq("async_u")
        ).only()
        assert found.id == u.id


def test_bind_advanced_where():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        User.create(name="A", age=1)
        User.create(name="B", age=2)
        rows = User.query().where(F(User).age.gt(1)).all()
        assert len(rows) == 1
        assert rows[0].name == "B"
