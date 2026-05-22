"""TraverseChain 多跳与 values 投影。"""

from __future__ import annotations

from entpy.runtime import Client
from examples.demos.gremlin.schemas import Person, GREMLIN_SCHEMAS


def test_traverse_chain_two_hops_sqlite():
    client = Client.open("sqlite:///:memory:", schemas=GREMLIN_SCHEMAS)
    client.migrate()
    alice = client.create(Person, name="Alice", city="NYC").save()
    bob = client.create(Person, name="Bob", city="SF").save()
    carol = client.create(Person, name="Carol", city="NYC").save()
    client.update(Person, alice.id).add("knows", bob.id).save()
    client.update(Person, bob.id).add("knows", carol.id).save()

    friends = client.traverse(alice).out("knows").values("name").all()
    assert friends == ["Bob"]

    fof = client.traverse(alice).out("knows").out("knows").all()
    assert len(fof) == 1
    assert fof[0].name == "Carol"

    # 兼容 traverse(entity, edge) 单跳写法
    one = client.traverse(alice, "knows").all()
    assert [p.name for p in one] == ["Bob"]
