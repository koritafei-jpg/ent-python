"""健壮性与 async/sync 对齐测试。"""

from __future__ import annotations

import pytest

from entpy.active import async_bind, bind, migrate, migrate_async
from entpy.privacy import Policy
from entpy.privacy.policy import rule
from entpy.runtime.errors import NotAllowedError
from entpy.runtime import Hook
from entpy.runtime.mutation import Mutation, Op
from entpy.privacy.policy import Deny, Skip
from examples.start.models import Group, User, Car, SCHEMAS


@Hook
def _stamp_create(next_mutator, mutation: Mutation):
    if mutation.op is Op.CREATE and "name" in mutation.fields:
        mutation.fields["name"] = mutation.fields["name"].upper()
    return next_mutator.mutate(mutation)


def _deny_delete(ctx, m: Mutation):
    if m.op in (Op.DELETE, Op.DELETE_ONE):
        raise Deny()
    raise Skip()


def test_async_create_applies_hook_fields():
    async def run():
        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            await migrate_async()
            from entpy.runtime.async_client import AsyncClient
            from entpy.active.context import get_async_client

            client: AsyncClient = get_async_client()
            client._hooks = [_stamp_create] + client._hooks
            u = await client.create(User, name="alice", age=1).save()
            assert u.name == "ALICE"

    import asyncio

    asyncio.run(run())


def test_async_delete_runs_policy():
    async def run():
        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            await migrate_async()
            from entpy.active.context import get_async_client

            client = get_async_client()
            client._policies = [Policy(mutation=[rule(_deny_delete)])]
            u = await client.create(User, name="x", age=1).save()
            with pytest.raises(NotAllowedError):
                await client.delete(User).one(u.id).execute()

    import asyncio

    asyncio.run(run())


def test_query_only_does_not_mutate_limit():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        User.create(name="a", age=1)
        User.create(name="b", age=2)
        User.query(name="a").only()
        rows = User.query().all()
        assert len(rows) == 2


def test_m2m_traverse_user_groups():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g = Group.create(name="g_valid")
        from entpy.active.context import get_client

        get_client().update(User, u.id).add("groups", g.id).save()
        loaded = u.out("groups").all()
        assert len(loaded) == 1
        assert loaded[0].name == "g_valid"


def test_entity_edge_uses_peer_schema():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        c = Car.create(model="M3", registered_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        from entpy.active.context import get_client

        get_client().update(User, u.id).add("cars", c.id).save()
        row = User.query(id=u.id).with_("cars").only()
        cars = row.cars
        assert cars[0]._schema is Car
