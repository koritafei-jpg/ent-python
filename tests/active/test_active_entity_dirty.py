"""ActiveEntity 脏字段：JSON/dict 原地修改。"""

from __future__ import annotations

from entpy.active import ActiveSchema, bind, migrate
from entpy.schema import BaseSchema, field


class Note(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("title").default(""),
            field.json_("metadata").default({}),
        ]


SCHEMAS = [Note]


def test_json_inplace_mutation_marks_dirty_on_save():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        note = Note.create(title="t", metadata={"k": "v"})
        note.save()
        note.metadata["k"] = "changed"
        note.save()
        refetched = Note.get(id=note.id)
        assert refetched.metadata["k"] == "changed"


def test_json_reassign_still_tracks_dirty():
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        note = Note.create(title="t", metadata={"a": 1})
        note.save()
        note.metadata = {"a": 2}
        note.save()
        refetched = Note.get(id=note.id)
        assert refetched.metadata == {"a": 2}
