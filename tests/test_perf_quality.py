"""性能与代码质量回归：缓存、builder 不可变、遍历健壮性。"""

from __future__ import annotations

import pytest

from entpy.active import bind, migrate
from entpy.active.context import get_effective_ctx, push_scope_ctx, reset_scope_ctx
from entpy.runtime.client import Client
from entpy.runtime.entity import Entity
from entpy.runtime.traverse import _hop_neighbors_batch
from examples.start.models import SCHEMAS, User


def test_effective_ctx_merge_is_cached():
    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        token = push_scope_ctx({"tenant": "a"})
        try:
            c1 = get_effective_ctx(client)
            c2 = get_effective_ctx(client)
            assert c1 is c2
            assert c1["tenant"] == "a"
        finally:
            reset_scope_ctx(token)
    finally:
        client.close()


def test_search_registry_cached_on_client():
    from examples.rag.models import SCHEMAS as RAG_SCHEMAS

    client = Client.open("sqlite:///:memory:", schemas=RAG_SCHEMAS)
    try:
        sr1 = client._get_search_registry()
        sr2 = client._get_search_registry()
        assert sr1 is sr2
    finally:
        client.close()


def test_query_only_does_not_mutate_builder_limit():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        User.create(name="only-me", age=1)
        from entpy.active.context import get_client

        client = get_client()
        qb = (
            client.query(User)
            .where(client.F(User).name.eq("only-me"))
            .limit(10)
        )
        qb.only()
        assert qb._limit == 10


def test_batch_neighbors_rejects_mixed_schema():
    from examples.start.models import Group

    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    try:
        u = Entity(User, {"id": 1, "name": "u", "age": 1}, client)
        g = Entity(Group, {"id": 1, "name": "g"}, client)
        with pytest.raises(ValueError, match="same schema"):
            _hop_neighbors_batch(client, [u, g], "groups")
    finally:
        client.close()
