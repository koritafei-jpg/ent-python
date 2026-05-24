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


def test_active_save_ignores_immutable_id_str_cast():
    from entpy.schema import BaseSchema, field

    class T(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [field.string("n").default("")]

    with bind("sqlite:///:memory:", schemas=[T]):
        migrate()
        t = T.create(n="a")
        t.save()
        t.id = str(t.id)
        t.save()
        assert T.get(id=t.id).n == "a"


def test_create_save_returns_vector_as_list_sqlite():
    from entpy.runtime import Client
    from entpy.schema import BaseSchema, field

    class Doc(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [field.vector("embedding", dimensions=2)]

    client = Client.open("sqlite:///:memory:", schemas=[Doc])
    try:
        client.migrate()
        row = client.create(Doc, embedding=[1.0, 2.0]).save()
        assert isinstance(row.embedding, list)
        assert row.embedding == [1.0, 2.0]
    finally:
        client.close()


def test_builder_isolates_json_before_save():
    class Note(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [
                field.string("title").default(""),
                field.json_("metadata").default({}),
            ]

    with bind("sqlite:///:memory:", schemas=[Note]):
        migrate()
        shared = {"k": 1}
        builder = get_client().create(Note, title="t2", metadata=shared)
        shared["k"] = 999
        row = builder.save()
        assert Note.get(id=row.id).metadata == {"k": 1}


def test_active_entity_init_isolates_json():
    class Note(ActiveSchema, BaseSchema):
        @classmethod
        def fields(cls):
            return [field.json_("metadata").default({})]

    with bind("sqlite:///:memory:", schemas=[Note]):
        migrate()
        from entpy.active.entity import ActiveEntity
        from entpy.active.context import get_client

        shared = {"k": 1}
        ae = ActiveEntity(Note, {"metadata": shared}, get_client(), _new=True)
        shared["k"] = 999
        ae.save()
        assert Note.get(id=ae.id).metadata == {"k": 1}


def test_resolve_connection_applies_runtime_hooks():
    from entpy.runtime.connect import ConnectRequest, resolve_connection
    from entpy.runtime.hook import hook

    @hook
    def stamp(next_m, m):
        if "name" in m.fields:
            m.fields["name"] = "STAMPED"
        return next_m.mutate(m)

    req = ConnectRequest(
        schemas=SCHEMAS,
        dsn="sqlite:///:memory:",
        runtime_hooks=[stamp],
    )
    client = resolve_connection(req)
    client.migrate()
    u = client.create(User, name="alice", age=1).save()
    assert u.name == "STAMPED"
    client.close()


def test_entity_strips_edges_from_data():
    from entpy.runtime.entity import Entity

    e = Entity(User, {"id": "x", "name": "a", "_edges": {"groups": []}})
    assert "_edges" not in e._data
    assert e._edges == {"groups": []}


def test_bind_client_hooks_do_not_accumulate():
    from entpy.active import bind_client
    from entpy.runtime.client import Client
    from entpy.runtime.hook import hook

    calls: list[int] = []

    @hook
    def inc(next_m, m):
        calls.append(1)
        return next_m.mutate(m)

    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    base_len = len(client._hooks)
    with bind_client(client, hooks=[inc]):
        client.create(User, name="a", age=1).save()
    with bind_client(client, hooks=[inc]):
        client.create(User, name="b", age=2).save()
    assert len(client._hooks) == base_len
    assert len(calls) == 2


def test_env_bind_without_dsn_raises(monkeypatch):
    monkeypatch.delenv("ENTPY_DSN", raising=False)
    monkeypatch.delenv("ENTPY_STORAGE", raising=False)
    monkeypatch.delenv("ENTPY_ASYNC", raising=False)
    with pytest.raises(RuntimeError, match="ENTPY_DSN"):
        with bind(schemas=SCHEMAS, source="env"):
            pass


@pytest.mark.asyncio
async def test_async_bind_rejects_sync_client():
    from entpy.active import async_bind
    from entpy.runtime.client import Client

    sync = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        async with async_bind(client=sync, schemas=SCHEMAS):
            pass
    except TypeError as e:
        assert "AsyncClient" in str(e)
    finally:
        sync.close()


def test_sync_bind_ignores_config_async_flag():
    """config['async'] 不得让 bind() 解析出 AsyncClient。"""
    with bind(
        config={"dsn": "sqlite:///:memory:", "async": True},
        schemas=SCHEMAS,
    ):
        migrate()
        u = User.create(name="sync", age=1)
        assert u.name == "sync"


def test_sync_bind_ignores_env_async_flag(monkeypatch):
    monkeypatch.setenv("ENTPY_DSN", "sqlite:///:memory:")
    monkeypatch.setenv("ENTPY_ASYNC", "true")
    with bind(schemas=SCHEMAS, source="env"):
        migrate()
        User.create(name="env-sync", age=1)


def test_active_schema_raises_under_async_bind_only():
    import asyncio

    async def run():
        from entpy.active import async_bind, migrate_async

        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            await migrate_async()
            with pytest.raises(RuntimeError, match="ActiveSchema"):
                User.create(name="x", age=1)

    asyncio.run(run())


def test_empty_update_is_noop_without_on_save():
    from entpy.observer import Observer
    from entpy.observer.registry import get_observer_registry

    class UObs(Observer):
        def __init__(self, st):
            super().__init__(st)
            self.saves = 0

        def on_save(self, mutation: Mutation) -> None:
            self.saves += 1

    reg = get_observer_registry()
    reg.register(User, UObs)
    try:
        with bind("sqlite:///:memory:", schemas=SCHEMAS):
            migrate()
            u = User.create(name="a", age=1)
            client = get_client()
            obs = client._observers[0]
            obs.saves = 0
            row = client.update(User, u.id).save()
            assert row.name == "a"
            assert obs.saves == 0
    finally:
        reg._by_schema.pop(User, None)


def test_bind_client_rejects_async_client():
    import asyncio

    async def run():
        from entpy.active import async_bind_client
        from entpy.runtime.async_client import AsyncClient

        ac = AsyncClient.open("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS)
        try:
            await ac.migrate()
            with pytest.raises(TypeError, match="bind_client"):
                from entpy.active import bind_client

                with bind_client(ac):
                    pass
        finally:
            await ac.aclose()

    asyncio.run(run())


def test_async_bind_client_rejects_sync_client():
    from entpy.active import async_bind_client, bind_client
    from entpy.runtime.client import Client

    sync = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        sync.migrate()

        async def run():
            with pytest.raises(TypeError, match="async_bind_client"):
                async with async_bind_client(sync):
                    pass

        import asyncio

        asyncio.run(run())
    finally:
        sync.close()


def test_migrate_rejects_async_bind_only():
    import asyncio

    async def run():
        from entpy.active import async_bind, migrate, migrate_async

        async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
            with pytest.raises(RuntimeError, match="migrate_async"):
                migrate()
            await migrate_async()

    asyncio.run(run())


def test_with_edges_cache_invalidated_after_link():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g1 = Group.create(name="alpha")
        g2 = Group.create(name="beta")
        row = User.query(id=u.id).with_("groups").only()
        assert row.groups == []
        row.link("groups", g1.id)
        assert [x.name for x in row.groups] == ["alpha"]
        row.set_links("groups", g2.id)
        assert [x.name for x in row.groups] == ["beta"]
        assert [x.name for x in row.out("groups").all()] == ["beta"]


def test_active_entity_edit_link_set_links():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g1 = Group.create(name="alpha")
        g2 = Group.create(name="beta")
        u.link("groups", g1.id)
        assert {x.name for x in u.out("groups").all()} == {"alpha"}
        u.set_links("groups", g2.id)
        assert {x.name for x in u.out("groups").all()} == {"beta"}
        u.edit().set("age", 99).save()
        assert User.get(id=u.id).age == 99


def test_link_flushes_dirty_fields_same_save():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g = Group.create(name="g")
        u.age = 42
        u.link("groups", g.id)
        loaded = User.get(id=u.id)
        assert loaded.age == 42
        assert [x.name for x in loaded.out("groups").all()] == ["g"]


def test_edit_add_flushes_dirty_fields():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g = Group.create(name="g")
        u.age = 7
        u.edit().add("groups", g.id).save()
        assert User.get(id=u.id).age == 7


@pytest.mark.asyncio
async def test_async_edit_add_flushes_dirty_fields():
    from entpy.active import async_bind, migrate_async
    from entpy.active.context import get_async_client

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        client = get_async_client()
        u = await client.create(User, name="U", age=1).save()
        g = await client.create(Group, name="g").save()
        from entpy.active.entity import ActiveEntity

        ae = ActiveEntity.from_entity(u)
        ae.age = 99
        await ae.edit().add("groups", g.id).save()
        ref = await client.query(User).where(client.F(User).id.eq(u.id)).only()
        assert ref.age == 99
        groups = await ref.out("groups").all()
        assert len(groups) == 1


def test_query_unknown_kw_field_value_error():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        with pytest.raises(ValueError, match="unknown field"):
            User.query(nosuch=1).all()


def test_add_unknown_edge_raises_at_call_time():
    import uuid

    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        client = get_client()
        with pytest.raises(ValueError, match="unknown edge"):
            client.update(User, u.id).add("nosuch", uuid.uuid4())
        with pytest.raises(ValueError, match="unknown edge"):
            client.create(User, name="x", age=1).add("nosuch", uuid.uuid4())


def test_entql_unknown_field_raises_value_error():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        with pytest.raises(ValueError, match="unknown field"):
            client.query(User).entql({"nosuch": 1}).all()


def test_entql_filter_must_be_dict():
    from entpy.entql.filter import entql_to_predicates

    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        with pytest.raises(ValueError, match="must be a dict"):
            entql_to_predicates(get_client().F(User), [])  # type: ignore[arg-type]


def test_entql_empty_or_matches_nothing():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        client = get_client()
        User.create(name="a", age=1)
        User.create(name="b", age=2)
        rows = client.query(User).entql({"or": []}).all()
        assert rows == []


def test_merge_mutation_respects_set_edges_replace():
    from entpy.runtime.hook import hook

    @hook
    def force_group(next_m, mutation):
        mutation.edges["groups"] = []
        return next_m.mutate(mutation)

    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        u = User.create(name="U", age=1)
        g1 = Group.create(name="alpha")
        g2 = Group.create(name="beta")
        client = get_client()
        client.update(User, u.id).add("groups", g1.id, g2.id).save()
        client._hooks = [force_group]
        client.update(User, u.id).set_edges("groups", g2.id).save()
        assert u.out("groups").all() == []


def test_entql_or_has_gremlin_fn():
    from entpy.entql.filter import entql_to_predicates
    from entpy.runtime import Client

    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        preds = entql_to_predicates(
            client.F(User), {"or": [{"name": "a"}, {"age": {"gt": 1}}]}
        )
        assert len(preds) == 1
        assert preds[0]._gremlin_fn is not None
        client.migrate()
        client.create(User, name="a", age=10).save()
        client.create(User, name="b", age=2).save()
        rows = client.query(User).where(preds[0]).all()
        assert {r.name for r in rows} == {"a", "b"}
    finally:
        client.close()


@pytest.mark.asyncio
async def test_async_empty_update_noop_returns_entity_not_coroutine():
    from entpy.active import async_bind, migrate_async
    from entpy.active.context import get_async_client

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        u = await get_async_client().create(User, name="noop", age=1).save()
        row = await get_async_client().update(User, u.id).save()
        import inspect

        assert not inspect.iscoroutine(row)
        assert row.name == "noop"


@pytest.mark.asyncio
async def test_traverse_update_module_api_rejects_async_bind():
    from entpy.active import async_bind, migrate_async, traverse, update
    from entpy.active.context import get_async_client

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        u = await get_async_client().create(User, name="a", age=1).save()
        with pytest.raises(RuntimeError, match="traverse"):
            traverse(u)
        with pytest.raises(RuntimeError, match="update"):
            update(User, u.id)


@pytest.mark.asyncio
async def test_search_and_f_work_under_async_bind():
    from entpy.active import async_bind, F, migrate_async, search
    from examples.rag.models import Chunk, SCHEMAS as RAG_SCHEMAS

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=RAG_SCHEMAS):
        await migrate_async()
        assert F(Chunk) is not None
        sb = search(Chunk)
        assert sb is not None


@pytest.mark.asyncio
async def test_active_entity_from_async_save_uses_persist():
    from entpy.active import async_bind, migrate_async
    from entpy.active.context import get_async_client
    from entpy.active.entity import ActiveEntity

    async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
        await migrate_async()
        row = await get_async_client().create(User, name="a", age=1).save()
        ae = ActiveEntity.from_entity(row)
        assert ae._async is True
        ae.name = "b"
        await ae.persist()
        ref = await get_async_client().query(User).where(
            get_async_client().F(User).name.eq("b")
        ).only()
        assert ref.name == "b"


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
