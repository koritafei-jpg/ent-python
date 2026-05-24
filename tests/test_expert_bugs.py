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
