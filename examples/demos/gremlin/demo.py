#!/usr/bin/env python3
"""演示 5：Gremlin — 图查询与多跳遍历。"""

from __future__ import annotations

import os
import sys

from entpy.active import bind, F, clear_graph, ensure_connection
from examples.demos.gremlin.models import Comment, Person, Post, GREMLIN_SCHEMAS
from examples.demos.gremlin.seed import seed
from examples.demos.common.print_observers import print_observer_events

GREMLIN_URL = os.environ.get("ENTPY_GREMLIN_URL", "ws://localhost:8182/gremlin")


def run_demo() -> None:
    ids = seed()

    print("\n=== 1. 图顶点查询 ===")
    for p in Person.query(city="NYC").all():
        print(f"  Person [{p.id}] {p.name}")

    print("\n=== 2. 一跳边 knows ===")
    alice = Person.get(name="Alice")
    friends = alice.out("knows").all()
    print(f"  Alice knows: {[f.name for f in friends]}")

    print("\n=== 3. 子表 — Post by author_id ===")
    for p in Post.query(author_id=ids["alice"]).all():
        print(f"  Post [{p.id}] {p.title}")

    print("\n=== 4. 子表 — Comment by post_id ===")
    for c in Comment.query(post_id=ids["post_tech"]).all():
        print(f"  Comment [{c.id}] {c.text}")

    print("\n=== 5. 多跳: Alice -knows-> friends ===")
    names = alice.out("knows").values("name").all()
    print(f"  direct friends: {names}")

    print("\n=== 6. 两跳 knows (friends-of-friends) ===")
    fof = alice.out("knows").out("knows").values("name").all()
    print(f"  friends-of-friends: {fof}")

    print("\n=== 7. 复合多跳: knows + 查好友的文章 ===")
    friend_ids = alice.out("knows").ids()
    if friend_ids:
        posts = Post.query().where(F(Post).author_id.in_(friend_ids)).all()
        print(f"  posts by Alice's friends: {[p.title for p in posts]}")

    print("\n=== 8. 三跳组合: knows + post/comment 子表 ===")
    for person in Person.query(city="NYC").all():
        for fr in person.out("knows").all():
            for post in Post.query(author_id=fr.id).all():
                n = len(Comment.query(post_id=post.id).all())
                print(
                    f"  {person.name} -> {fr.name} -> post '{post.title}' -> {n} comment(s)"
                )

    print_observer_events()


def main() -> None:
    print("演示 5 — Gremlin 图数据库")
    try:
        with bind(GREMLIN_URL, schemas=GREMLIN_SCHEMAS, storage="gremlin"):
            ensure_connection()
            clear_graph("persons", "posts", "comments")
            run_demo()
    except Exception as e:
        print(f"Skip: cannot connect to {GREMLIN_URL}: {e}", file=sys.stderr)
        print("Start: docker compose -f docker-compose.gremlin.yml up -d")
        sys.exit(0)


if __name__ == "__main__":
    main()
