"""§14.6：复杂边 SQL 回退与 Gremlin Update 单次返回。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from entpy.dialect.gremlin import graph_ops
from entpy.dialect.sqlalchemy import sqlgraph
from entpy.dialect.sqlalchemy.spec import UpdateSpec
from entpy.ir.graph import ResolvedEdge
from entpy.runtime import Client
from entpy.schema.edge import RelType
from examples.demos.gremlin.models import Person, GREMLIN_SCHEMAS


def test_edge_joinable_sql_rejects_m2m_without_join():
    edge = ResolvedEdge(
        name="bad",
        rel=RelType.M2M,
        inverse=False,
        owner=MagicMock(),
        peer=MagicMock(),
        ref=None,
        unique=False,
        fk_columns=["group_id"],
        join_table=None,
    )
    assert sqlgraph.edge_joinable_sql(edge) is False
    assert sqlgraph.can_traverse_chain_sql([edge, edge]) is False


def test_traverse_chain_sql_fast_path_valueerror_falls_back(monkeypatch):
    """JOIN 编译失败时回退 Python 逐跳，结果仍正确。"""
    client = Client.open("sqlite:///:memory:", schemas=GREMLIN_SCHEMAS)
    try:
        client.migrate()
        alice = client.create(Person, name="Alice", city="NYC").save()
        bob = client.create(Person, name="Bob", city="SF").save()
        carol = client.create(Person, name="Carol", city="NYC").save()
        client.update(Person, alice.id).add("knows", bob.id).save()
        client.update(Person, bob.id).add("knows", carol.id).save()

        def _boom(*_args, **_kwargs):
            raise ValueError("cannot compile to SQL JOIN")

        monkeypatch.setattr(sqlgraph, "traverse_chain_sql", _boom)
        fof = alice.out("knows").out("knows").all()
        assert len(fof) == 1
        assert fof[0].name == "Carol"
    finally:
        client.close()


def test_gremlin_update_node_returns_row_without_get_by_id(monkeypatch):
    """字段更新与 valueMap 同链；不调用 get_by_id。"""
    monkeypatch.setattr(
        graph_ops,
        "get_by_id",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("get_by_id should not be used after update_node")
        ),
    )

    g = MagicMock()
    trav = g.V.return_value
    trav.hasLabel.return_value = trav
    trav.hasNext.return_value = True
    trav.property.return_value = trav
    trav.valueMap.return_value = trav
    trav.next.return_value = {"id": ["vid-1"], "name": ["updated"]}

    registry = MagicMock()
    spec = UpdateSpec(table="persons", id="vid-1", fields={"name": "updated"}, edges=[])

    row = graph_ops.update_node(g, registry, spec)
    assert row is not None
    assert row["name"] == "updated"
    trav.property.assert_called()
    trav.valueMap.assert_called_with(True)
