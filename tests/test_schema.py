from entpy.ir import build_graph, load_schemas
from examples.start.models import User, Car, Group, SCHEMAS


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


def test_graph_car_owner_fk():
    g = build_graph(SCHEMAS)
    owner_edges = [e for e in g.edges if e.owner.name == "Car" and e.name == "owner"]
    assert len(owner_edges) == 1
    assert owner_edges[0].fk_columns == ["user_cars"]
    assert owner_edges[0].inverse is True


def test_graph_m2m_bidirectional_edges():
    from entpy.schema.edge import RelType

    g = build_graph(SCHEMAS)
    user_groups = [e for e in g.edges if e.owner.name == "User" and e.name == "groups"]
    group_users = [e for e in g.edges if e.owner.name == "Group" and e.name == "users"]
    assert len(user_groups) == 1 and user_groups[0].rel == RelType.M2M
    assert len(group_users) == 1 and group_users[0].rel == RelType.M2M
    assert user_groups[0].join_columns == ["group_id", "user_id"]
    assert group_users[0].join_columns == ["user_id", "group_id"]
