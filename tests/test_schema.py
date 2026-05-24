from entpy.ir import build_graph, load_schemas
from examples.start.schemas import User, Car, Group, SCHEMAS


def test_load_start_schemas():
    nodes = load_schemas(SCHEMAS)
    assert len(nodes) == 3
    user = next(n for n in nodes if n.name == "User")
    assert any(f.name == "age" for f in user.fields)
    assert any(f.name == "id" for f in user.fields)
    assert any(f.name == "create_time" for f in user.fields)
    assert any(f.name == "delete_time" for f in user.fields)


def test_graph_fk_user_cars():
    g = build_graph(SCHEMAS)
    assert any(e.fk_columns == ["user_cars"] for e in g.edges)


def test_graph_m2m_join():
    g = build_graph(SCHEMAS)
    assert "group_users" in g.join_tables
