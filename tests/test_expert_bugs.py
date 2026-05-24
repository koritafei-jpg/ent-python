"""测试专家视角：框架实现级回归。"""

from __future__ import annotations

import uuid

import pytest

from entpy.active import ActiveSchema, bind, migrate
from entpy.active.context import get_client
from entpy.active.entity import ActiveEntity
from entpy.runtime.errors import NotFoundError
from entpy.runtime.mutation import Mutation, Op
from entpy.runtime.validation import merge_mutation_into_builder, snapshot_edges
from entpy.schema import BaseSchema, field
from examples.start.models import User, Group, SCHEMAS


def test_merge_mutation_does_not_duplicate_shared_edge_lists():
    edges = {"groups": ["g1"]}
    mutation = Mutation(User, Op.UPDATE_ONE, id=1, edges=snapshot_edges(edges))
    merge_mutation_into_builder(mutation, fields={}, edges=edges)
    assert edges["groups"] == ["g1"]


def test_update_save_does_not_duplicate_m2m_edge_ids_in_builder():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g = Group.create(name="g")
        client = get_client()
        builder = client.update(User, u.id).add("groups", g.id)
        builder.save()
        assert builder._edges.get("groups") == [g.id]


def test_update_missing_uuid_raises_not_found():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        with pytest.raises(NotFoundError):
            get_client().update(User, id=uuid.uuid4()).set("name", "ghost").save()


class Note(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("title").default(""),
            field.json_("metadata").default({}),
        ]


def test_from_entity_isolates_json_from_source_entity():
    with bind("sqlite:///:memory:", schemas=[Note]):
        migrate()
        note = Note.create(title="t", metadata={"k": 1})
        note.save()
        loaded = Note.query(title="t").only()
        copy = ActiveEntity.from_entity(loaded)
        copy.metadata["k"] = 99
        assert loaded.metadata["k"] == 1


def test_active_new_isolates_json_from_caller_dict():
    with bind("sqlite:///:memory:", schemas=[Note]):
        migrate()
        shared = {"k": 1}
        n = Note.new(metadata=shared)
        shared["k"] = 99
        assert n.metadata["k"] == 1


def test_update_hook_does_not_persist_unset_fields():
    from entpy.runtime.hook import hook

    @hook
    def touch_name(next_m, mutation):
        mutation.fields["name"] = mutation.fields.get("name", "X") + "!"
        return next_m.mutate(mutation)

    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="Original", age=1)
        client = get_client()
        client._hooks = [touch_name]
        updated = client.update(User, u.id).set("age", 99).save()
        assert updated.name == "Original"
        assert updated.age == 99


def test_inverse_traverse_reads_fk_from_database():
    from datetime import datetime, timezone

    from examples.start.models import Car

    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u1 = User.create(name="U1", age=1)
        u2 = User.create(name="U2", age=2)
        c = Car.create(model="M", registered_at=datetime.now(timezone.utc))
        get_client().update(User, u1.id).add("cars", c.id).save()
        c = Car.get(id=c.id)
        get_client().update(Car, c.id).set("user_cars", u2.id).save()
        c._data["user_cars"] = u1.id
        assert [o.name for o in c.out("owner").all()] == ["U2"]


def test_traverse_out_reflects_edges_after_update():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g = Group.create(name="g")
        loaded = User.query(id=u.id).with_("groups").only()
        assert len(loaded.groups) == 0
        get_client().update(User, u.id).add("groups", g.id).save()
        assert len(u.out("groups").all()) == 1


@pytest.mark.asyncio
async def test_async_query_with_interceptor():
    import asyncio

    from entpy.active import async_bind, migrate_async
    from entpy.active.context import get_async_client
    from entpy.runtime.interceptor import Interceptor

    def cap(next_q, req):
        req.limit = 1
        return next_q.query(req)

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        client = get_async_client()
        client._interceptors = [Interceptor(cap)]
        await client.create(User, name="a", age=1).save()
        await client.create(User, name="b", age=2).save()
        rows = await client.query(User).all()
        assert len(rows) == 1
