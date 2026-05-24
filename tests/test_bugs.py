"""回归测试：已发现的生产级 bug。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from entpy.active import bind, migrate
from entpy.active.context import get_client
from entpy.observer import Observer
from entpy.observer.registry import get_observer_registry
from entpy.runtime import Client
from entpy.runtime.errors import NotFoundError
from entpy.runtime.mutation import Mutation, Op
from entpy.schema import BaseSchema, field
from entpy.active import ActiveSchema
from examples.start.models import User, Car, Group, SCHEMAS


def test_m2m_group_add_users_both_directions():
    """Group.add('users') 与 User.add('groups') 均应正确写入 join 表。"""
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        g = Group.create(name="g_valid")
        u = User.create(name="U", age=1)
        get_client().update(Group, g.id).add("users", u.id).save()
        assert [x.name for x in g.out("users").all()] == ["U"]

        g2 = Group.create(name="g_two")
        get_client().update(User, u.id).add("groups", g2.id).save()
        assert {x.name for x in u.out("groups").all()} == {"g_valid", "g_two"}


def test_inverse_edge_car_to_owner():
    """Car.out('owner') 应沿 Car 表上的 FK 解析到 User。"""
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="Owner", age=30)
        c = Car.create(model="M3", registered_at=datetime.now(timezone.utc))
        get_client().update(User, u.id).add("cars", c.id).save()
        c = Car.get(id=c.id)
        assert c.user_cars == u.id
        owners = c.out("owner").all()
        assert len(owners) == 1
        assert owners[0].name == "Owner"


def test_with_cars_loads_peer_schema():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        c = Car.create(model="X", registered_at=datetime.now(timezone.utc))
        get_client().update(User, u.id).add("cars", c.id).save()
        loaded = User.query(id=u.id).with_("cars").only()
        assert loaded.cars[0]._schema is Car
        assert loaded.cars[0].model == "X"


def test_delete_missing_id_no_on_delete():
    class Tmp(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [field.string("n")]

    class TmpObserver(Observer):
        def __init__(self, schema_type):
            super().__init__(schema_type)
            self.deletes = 0

        def on_delete(self, mutation: Mutation) -> None:
            self.deletes += 1

    registry = get_observer_registry()
    registry.register(Tmp, TmpObserver)
    try:
        client = Client.open("sqlite:///:memory:", schemas=[Tmp])
        client.migrate()
        import uuid

        missing = uuid.uuid4()
        n = client.delete(Tmp).one(missing).execute()
        assert n == 0
        assert client._observers[0].deletes == 0
    finally:
        registry._by_schema.pop(Tmp, None)


def test_update_missing_id_raises_not_found():
    import uuid

    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        with pytest.raises(NotFoundError):
            client.update(User, id=uuid.uuid4()).set("name", "ghost").save()


def test_m2m_duplicate_add_idempotent():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g = Group.create(name="g_valid")
        client = get_client()
        client.update(User, u.id).add("groups", g.id).save()
        client.update(User, u.id).add("groups", g.id).save()
        assert len(u.out("groups").all()) == 1


def test_m2m_set_edges_replaces():
    """set_edges 全量替换 M2M；add() 仍为追加。"""
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        u = User.create(name="U", age=1)
        g1 = Group.create(name="alpha")
        g2 = Group.create(name="beta")
        client.update(User, u.id).add("groups", g1.id, g2.id).save()
        assert {x.name for x in u.out("groups").all()} == {"alpha", "beta"}

        client.update(User, u.id).set_edges("groups", g2.id).save()
        assert {x.name for x in u.out("groups").all()} == {"beta"}

        client.update(User, u.id).set_edges("groups", g1.id).add("groups", g2.id).save()
        assert {x.name for x in u.out("groups").all()} == {"alpha", "beta"}


def test_m2m_set_edges_clear():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        u = User.create(name="U", age=1)
        g = Group.create(name="alpha")
        client.update(User, u.id).add("groups", g.id).save()
        assert len(u.out("groups").all()) == 1
        client.update(User, u.id).set_edges("groups").save()
        assert u.out("groups").all() == []


def test_set_edges_rejects_non_m2m():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        c = Car.create(model="X", registered_at=datetime.now(timezone.utc))
        with pytest.raises(TypeError, match="M2M"):
            get_client().update(User, u.id).set_edges("cars", c.id)


def test_delete_one_and_where_raises():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="x", age=1)
        client = get_client()
        with pytest.raises(ValueError, match="not both"):
            client.delete(User).one(u.id).where(client.F(User).name.eq("x")).execute()


def test_delete_where_no_match_no_on_delete():
    class Tmp(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [field.string("n")]

    class TmpObserver(Observer):
        def __init__(self, schema_type):
            super().__init__(schema_type)
            self.deletes = 0

        def on_delete(self, mutation: Mutation) -> None:
            self.deletes += 1

    registry = get_observer_registry()
    registry.register(Tmp, TmpObserver)
    try:
        client = Client.open("sqlite:///:memory:", schemas=[Tmp])
        client.migrate()
        n = client.delete(Tmp).where(client.F(Tmp).n.eq("missing")).execute()
        assert n == 0
        assert client._observers[0].deletes == 0
    finally:
        registry._by_schema.pop(Tmp, None)
