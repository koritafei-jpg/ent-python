from datetime import datetime, timezone

from entpy.runtime import Client
from examples.start.schemas import User, Car, Group, SCHEMAS


def test_start_create_query():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()

    u = client.create(User, name="Alice", age=30).save()
    assert u.id is not None
    assert u.name == "Alice"

    found = client.query(User).where(client.F(User).name.eq("Alice")).only()
    assert found.age == 30


def test_start_o2m_cars():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()

    u = client.create(User, name="Bob", age=25).save()
    c = client.create(
        Car, model="Tesla", registered_at=datetime.now(timezone.utc)
    ).save()
    client.update(User, u.id).add("cars", c.id).save()

    loaded = client.query(User).where(client.F(User).id.eq(u.id)).with_("cars").only()
    assert len(loaded._edges.get("cars", [])) == 1
    assert loaded._edges["cars"][0]["model"] == "Tesla"


def test_start_m2m_groups():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()

    u = client.create(User, name="Carol", age=40).save()
    g = client.create(Group, name="admins").save()
    client.update(User, u.id).add("groups", g.id).save()

    loaded = client.query(User).where(client.F(User).id.eq(u.id)).with_("groups").only()
    assert len(loaded._edges.get("groups", [])) == 1
