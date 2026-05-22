"""删除、遍历、hooks、混入、privacy、entql、异步。"""

from __future__ import annotations

import pytest

from datetime import datetime

from entpy.runtime import Client, AsyncClient, Hook, Interceptor
from entpy.runtime.interceptor import QueryRequest
from entpy.runtime.mutation import Mutation, Op
from entpy.privacy import Policy, always_deny, always_allow, Allow, Deny, Skip
from entpy.privacy.policy import rule
from entpy.runtime.errors import NotAllowedError
from entpy.schema import Schema, field, CreateTimeMixin
from examples.start.schemas import User, Car, Group, SCHEMAS


@Hook
def audit_hook(next_mutator, mutation: Mutation):
    if mutation.op == Op.CREATE and "name" in mutation.fields:
        mutation.fields["name"] = mutation.fields["name"].upper()
    return next_mutator.mutate(mutation)


def _deny_create(ctx, m):
    if m.op == Op.CREATE:
        raise Deny()
    raise Skip()


class DenyCreateUser(User):
    @classmethod
    def policy(cls):
        return Policy(mutation=[rule(_deny_create)])


class TimedUser(User, CreateTimeMixin):
    @classmethod
    def fields(cls):
        return User.fields() + CreateTimeMixin.fields()


TIMED_SCHEMAS = [TimedUser, Car, Group]


def test_delete_by_where():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    client.create(User, name="del_me", age=1).save()
    client.create(User, name="keep", age=2).save()
    n = client.delete(User).where(client.F(User).name.eq("del_me")).execute()
    assert n == 1
    assert len(client.query(User).all()) == 1


def test_traverse_cars():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    u = client.create(User, name="T", age=1).save()
    c = client.create(Car, model="X", registered_at=datetime(2020, 1, 1)).save()
    client.update(User, u.id).add("cars", c.id).save()
    u2 = client.query(User).where(client.F(User).id.eq(u.id)).with_("cars").only()
    cars = client.traverse(u2, "cars").all()
    assert len(cars) == 1
    assert cars[0].model == "X"


def test_hook_mutate_name():
    client = Client.open_with("sqlite:///:memory:", schemas=SCHEMAS, hooks=[audit_hook])
    client.migrate()
    u = client.create(User, name="alice", age=1).save()
    assert u.name == "ALICE"


def test_create_time_mixin():
    client = Client.open("sqlite:///:memory:", schemas=TIMED_SCHEMAS)
    client.migrate()
    u = client.create(TimedUser, name="t", age=1).save()
    assert u.create_time is not None


def test_privacy_deny_create():
    client = Client.open("sqlite:///:memory:", schemas=[DenyCreateUser, Car, Group])
    client.migrate()
    with pytest.raises(NotAllowedError):
        client.create(DenyCreateUser, name="x", age=1).save()


def test_entql_filter():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    client.create(User, name="entql_a", age=10).save()
    client.create(User, name="entql_b", age=20).save()
    rows = client.query(User).entql({"name": "entql_a"}).all()
    assert len(rows) == 1


def test_interceptor_limit():
    def cap_fn(next_q, req: QueryRequest):
        if req.limit is None:
            req.limit = 1
        return next_q.query(req)

    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client._interceptors = [Interceptor(cap_fn)]
    client.migrate()
    client.create(User, name="a", age=1).save()
    client.create(User, name="b", age=2).save()
    rows = client.query(User).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_async_client():
    client = AsyncClient.open("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS)
    await client.migrate()
    u = await client.create(User, name="async_u", age=5).save()
    found = await client.query(User).where(client.F(User).name.eq("async_u")).only()
    assert found.id == u.id


def test_gremlin_driver_smoke():
    pytest.importorskip("gremlinpython")
    from entpy.dialect.gremlin.driver import GremlinDriver
    from entpy.runtime.registry import Registry
    from examples.start.schemas import SCHEMAS

    reg = Registry.from_schemas(SCHEMAS)
    d = GremlinDriver("ws://localhost:8182/gremlin", reg)
    try:
        d._ensure()
    except Exception:
        pytest.skip("gremlin server not running")
