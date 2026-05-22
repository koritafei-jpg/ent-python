"""社交图种子数据（update/traverse 建边）。"""

from __future__ import annotations

from entpy.active import update
from examples.demos.gremlin.schemas import Comment, Person, Post


def seed() -> dict[str, int]:
    alice = Person.create(name="Alice", city="NYC")
    bob = Person.create(name="Bob", city="SF")
    carol = Person.create(name="Carol", city="NYC")

    update(Person, alice.id).add("knows", bob.id).save()
    update(Person, bob.id).add("knows", carol.id).save()

    p1 = Post.create(title="entpy graph", topic="tech", author_id=alice.id)
    Post.create(title="SF food", topic="life", author_id=bob.id)
    Comment.create(text="nice post", post_id=p1.id)

    return {"alice": alice.id, "bob": bob.id, "carol": carol.id, "post_tech": p1.id}
