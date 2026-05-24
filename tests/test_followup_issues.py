"""上轮「建议后续」项回归。"""

from __future__ import annotations

import pytest

from entpy.runtime import Client
from entpy.search.semantic import SEMANTIC_BRUTE_MAX_ROWS, SemanticBackend
from examples.rag.models import Chunk, SCHEMAS


def test_semantic_brute_requires_sqlite_opt_in():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    client.migrate()
    table = client._registry.table_for(Chunk)
    engine = create_engine("sqlite:///:memory:")
    meta, _ = __import__(
        "entpy.dialect.sqlalchemy.metadata", fromlist=["build_metadata"]
    ).build_metadata(client._registry.graph)
    meta.create_all(engine)
    sem = SemanticBackend()
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="allow_brute_fallback"):
            sem.search(
                session,
                table,
                "embedding",
                [0.0] * 8,
                None,
                allow_brute_fallback=False,
            )


def test_semantic_brute_row_cap():
    from sqlalchemy import Column, Integer, MetaData, Table, create_engine
    from sqlalchemy.orm import Session

    meta = MetaData()
    t = Table("big", meta, Column("id", Integer, primary_key=True), Column("embedding", Integer))
    engine = create_engine("sqlite:///:memory:")
    meta.create_all(engine)
    with Session(engine) as session:
        for i in range(SEMANTIC_BRUTE_MAX_ROWS + 1):
            session.execute(t.insert().values(id=i, embedding=1))
        session.commit()
    sem = SemanticBackend()
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="brute semantic scan refused"):
            sem._search_brute_table(session, t, "embedding", [1.0], top_k=1)


def test_gremlin_load_edge_neighbors_batch_groups(monkeypatch):
    pytest.importorskip("gremlinpython")
    from entpy.dialect.gremlin import graph_ops
    from entpy.ir.graph import ResolvedEdge
    from entpy.schema.edge import RelType

    class FakeG:
        def V(self, *args):
            return self

        def group(self):
            return self

        def by(self, *args, **kwargs):
            return self

        def next(self):
            return {1: [{"name": ["peer"], "id": [2]}]}

    class FakePeer:
        resolved_table = lambda self: "peer"

    edge = ResolvedEdge(
        name="knows",
        rel=RelType.M2M,
        peer=FakePeer(),
        fk_columns=[],
        join_table="jt",
        join_columns=["a", "b"],
        inverse=False,
    )
    monkeypatch.setattr(graph_ops, "edge_label", lambda e: "knows")
    monkeypatch.setattr(graph_ops, "vertex_label", lambda p: "peer")
    out = graph_ops.load_edge_neighbors_batch(FakeG(), None, [1], edge)
    assert 1 in out
    assert out[1][0]["name"] == "peer"
