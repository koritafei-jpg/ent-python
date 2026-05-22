"""关系库演示种子数据。"""

from __future__ import annotations

from examples.demos.relational.schemas import Article, Author, Comment


def seed() -> dict[str, int]:
    a_us = Author.create(name="Alice", region="US")
    a_eu = Author.create(name="Bob", region="EU")

    art1 = Article.create(
        title="entpy SQL guide",
        body="Runtime-first entity framework",
        status="published",
        author_id=a_us.id,
    )
    Comment.create(body="Great intro", rating=5, article_id=art1.id)
    Comment.create(body="More examples please", rating=4, article_id=art1.id)

    Article.create(
        title="Draft notes",
        body="work in progress",
        status="draft",
        author_id=a_us.id,
    )

    art3 = Article.create(
        title="Gremlin overview",
        body="Graph traversal with TinkerPop",
        status="published",
        author_id=a_eu.id,
    )
    Comment.create(body="Needs translation", rating=3, article_id=art3.id)

    return {"author_us": a_us.id, "article_published": art1.id}
