#!/usr/bin/env python3
"""演示 1：关系库 — 查询、复杂查询、子表（FK 子行）。"""

from __future__ import annotations

from entpy.active import bind, migrate, F
from examples.demos.relational.schemas import Article, Author, Comment, SCHEMAS
from examples.demos.relational.seed import seed


def main() -> None:
    print("演示 1 — 关系数据库（SQL）")
    with bind("sqlite:///:memory:", schemas=SCHEMAS):
        migrate()
        seed()

        print("\n=== 1. 简单查询 ===")
        for a in Article.query(status="published").all():
            print(f"  [{a.id}] {a.title}")

        print("\n=== 2. 复杂查询 (多条件) ===")
        rows = (
            Article.query(status="published")
            .where(F(Article).author_id.eq(1))
            .all()
        )
        print(f"  published by author 1: {len(rows)} row(s)")

        print("\n=== 3. EntQL ===")
        entql_rows = Article.query().entql({"status": "published"}).all()
        print(f"  entql published: {len(entql_rows)}")

        print("\n=== 4. 子表查询 (Comment.article_id) ===")
        art = Article.get(title="entpy SQL guide")
        for c in Comment.query(article_id=art.id).all():
            print(f"  comment [{c.id}] rating={c.rating} body={c.body}")

        print("\n=== 5. 子表复杂条件 (rating >= 4) ===")
        good = (
            Comment.query(article_id=art.id)
            .where(F(Comment).rating.gt(4))
            .all()
        )
        print(f"  high-rating comments: {len(good)}")

        print("\n=== 6. 跨表复杂查询 (US 作者的文章) ===")
        us_ids = [a.id for a in Author.query(region="US").all()]
        if us_ids:
            us_articles = (
                Article.query(status="published")
                .where(F(Article).author_id.in_(us_ids))
                .all()
            )
            print(f"  US published articles: {[a.title for a in us_articles]}")


if __name__ == "__main__":
    main()
