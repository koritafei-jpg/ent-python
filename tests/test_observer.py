"""Observer 自动发现与生命周期。"""

from __future__ import annotations

from entpy.active import ActiveSchema, bind, migrate
from entpy.observer import Observer, discover_observers, infer_observer_packages, observes
from entpy.runtime import Client
from entpy.observer.registry import get_observer_registry
from entpy.runtime.mutation import Mutation, Op
from entpy.schema import BaseSchema, field
from entpy.schema.base import Schema
from examples.start.models import User, SCHEMAS


def test_infer_observer_packages():
    pkgs = infer_observer_packages(SCHEMAS)
    assert "examples.start.observers" in pkgs


def test_discover_user_observer():
    observers = discover_observers([User])
    assert len(observers) == 1
    assert observers[0].schema_type is User


def test_user_observer_trim_name_on_create():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="  Alice  ", age=30)
        assert u.name == "Alice"


def test_observes_decorator_registers():
    class Temp(Schema):
        @classmethod
        def fields(cls):
            return [field.string("x")]

    class TempObserver(Observer):
        def creating(self, mutation: Mutation) -> None:
            mutation.fields["x"] = "ok"

    registry = get_observer_registry()
    registry.register(Temp, TempObserver)
    try:
        obs = discover_observers([Temp])
        assert len(obs) == 1
        m = Mutation(Temp, Op.CREATE, fields={"x": "bad"})
        obs[0].creating(m)
        assert m.fields["x"] == "ok"
    finally:
        registry._by_schema.pop(Temp, None)


def test_on_save_on_delete_callbacks():
    class Tmp(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [field.string("n")]

    class TmpObserver(Observer):
        def __init__(self, schema_type):
            super().__init__(schema_type)
            self.saves = 0
            self.deletes = 0

        def on_save(self, mutation: Mutation) -> None:
            self.saves += 1

        def on_delete(self, mutation: Mutation) -> None:
            self.deletes += 1

    registry = get_observer_registry()
    registry.register(Tmp, TmpObserver)
    try:
        client = Client.open("sqlite:///:memory:", schemas=[Tmp])
        client.migrate()
        row = client.create(Tmp, n="x").save()
        client.delete(Tmp).one(row.id).execute()
        obs = client._observers[0]
        assert obs.saves == 1
        assert obs.deletes == 1
    finally:
        registry._by_schema.pop(Tmp, None)


def test_discover_demo_relational_observers():
    from examples.demos.relational.models import Author, SCHEMAS as REL_SCHEMAS

    names = {o.schema_type.__name__ for o in discover_observers(REL_SCHEMAS)}
    assert names == {"Author", "Article", "Comment"}


def test_observes_decorator_via_decorator():
    class Other(Schema):
        @classmethod
        def fields(cls):
            return [field.string("n")]

    @observes(Other)
    class OtherObserver(Observer):
        def creating(self, mutation: Mutation) -> None:
            mutation.fields["n"] = "from_observer"

    try:
        obs = discover_observers([Other])
        assert obs[0].schema_type is Other
    finally:
        get_observer_registry()._by_schema.pop(Other, None)
