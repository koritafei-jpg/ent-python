"""大项重构：traverse 共享、async interceptor、O2O 边更新。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from entpy.active import bind, migrate
from entpy.active.context import get_client
from entpy.runtime.entity import Entity
from entpy.runtime.interceptor import AsyncInterceptor, Interceptor, QueryRequest
from examples.start.models import Car, SCHEMAS, User


def test_query_request_carries_predicates():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        User.create(name="a", age=1)
        User.create(name="b", age=2)
        client = get_client()
        seen: list[QueryRequest] = []

        @Interceptor
        def cap(next_q, req):
            seen.append(req)
            return next_q.query(req)

        client._interceptors = [cap]
        rows = client.query(User).where(client.F(User).name.eq("a")).all()
        assert len(rows) == 1
        assert len(seen) == 1
        assert len(seen[0].predicates) == 1


@pytest.mark.asyncio
async def test_async_interceptor_chain_native():
    from entpy.active import async_bind, migrate_async
    from entpy.active.context import get_async_client
    from entpy.runtime.query_exec import execute_query_async
    from entpy.runtime.interceptor import QueryRequest

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        client = get_async_client()
        await client.create(User, name="x", age=1).save()
        seen: list[QueryRequest] = []

        @AsyncInterceptor
        async def cap(next_q, req):
            seen.append(req)
            return await next_q.query(req)

        client._interceptors = [cap]
        req = QueryRequest(schema=User, predicates=[])
        rows = await execute_query_async(
            client, User, [], limit=None, with_edges=[], request=req
        )
        assert len(rows) == 1
        assert len(seen) == 1


def test_o2o_edge_update_replaces_exclusive_peer():
    """独占 O2O（Car.owner）更新时解除旧 peer 的 FK。"""
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u1 = User.create(name="U1", age=1)
        u2 = User.create(name="U2", age=2)
        c = Car.create(model="M", registered_at=datetime.now(timezone.utc))
        client = get_client()
        client.update(User, u1.id).add("cars", c.id).save()
        assert Car.get(id=c.id).user_cars == u1.id
        client.update(User, u2.id).add("cars", c.id).save()
        c2 = Car.get(id=c.id)
        assert c2.user_cars == u2.id
        assert len(u1.out("cars").all()) == 0
        assert len(u2.out("cars").all()) == 1
