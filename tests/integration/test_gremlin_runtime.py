"""Gremlin 存储上的 start 示例集成测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from entpy.runtime import Client
from examples.start.schemas import User, Car, Group, SCHEMAS

GREMLIN_URL = "ws://localhost:8182/gremlin"


@pytest.fixture
def gremlin_client():
    pytest.importorskip("gremlinpython")
    client = Client.open(GREMLIN_URL, schemas=SCHEMAS, storage="gremlin")
    try:
        client._driver._ensure()
    except Exception as exc:
        pytest.skip(f"gremlin server not running: {exc}")
    g = client._driver.g
    for label in ("users", "cars", "groups", "group_users"):
        g.V().hasLabel(label).drop().iterate()
    yield client
    client._driver.close()


@pytest.mark.gremlin
def test_gremlin_create_query(gremlin_client):
    u = gremlin_client.create(User, name="Alice", age=30).save()
    assert u.id is not None
    found = gremlin_client.query(User).where(
        gremlin_client.F(User).name.eq("Alice")
    ).only()
    assert found.age == 30


@pytest.mark.gremlin
def test_gremlin_o2m_cars(gremlin_client):
    u = gremlin_client.create(User, name="Bob", age=25).save()
    c = gremlin_client.create(
        Car, model="Tesla", registered_at=datetime(2024, 1, 1)
    ).save()
    gremlin_client.update(User, u.id).add("cars", c.id).save()

    loaded = gremlin_client.query(User).where(
        gremlin_client.F(User).id.eq(u.id)
    ).with_("cars").only()
    assert len(loaded._edges.get("cars", [])) == 1
    assert loaded._edges["cars"][0]["model"] == "Tesla"


@pytest.mark.gremlin
async def test_gremlin_async_client(gremlin_client):
    from entpy.runtime import AsyncClient

    client = AsyncClient.open(
        GREMLIN_URL, schemas=SCHEMAS, storage="gremlin"
    )
    try:
        client._driver._ensure()
    except Exception as exc:
        pytest.skip(f"gremlin server not running: {exc}")
    g = client._driver.g
    for label in ("users", "cars", "groups", "group_users"):
        g.V().hasLabel(label).drop().iterate()
    u = await client.create(User, name="Async", age=1).save()
    found = await client.query(User).where(
        client.F(User).name.eq("Async")
    ).only()
    assert found.id == u.id
    await client._driver.close()


@pytest.mark.gremlin
def test_gremlin_m2m_groups(gremlin_client):
    u = gremlin_client.create(User, name="Carol", age=40).save()
    g = gremlin_client.create(Group, name="admins").save()
    gremlin_client.update(User, u.id).add("groups", g.id).save()

    loaded = gremlin_client.query(User).where(
        gremlin_client.F(User).id.eq(u.id)
    ).with_("groups").only()
    assert len(loaded._edges.get("groups", [])) == 1
