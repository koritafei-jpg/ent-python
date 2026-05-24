#!/usr/bin/env python3
"""演示 1：关系库 — 查询、复杂查询、子表（FK 子行）。"""

from __future__ import annotations

from entpy.active import migrate, F
from examples.demos.relational.models import Article, Author, Comment, SCHEMAS
from examples.demos.relational.seed import seed
from examples.demos.common.connect import demo_bind
from examples.demos.common.print_observers import print_observer_events


def main() -> None:
    print("演示 1 — 关系数据库（SQL）")
    with demo_bind(SCHEMAS):
        migrate()
        ids = seed()

        print("\n=== 1. 简单查询 ===")
        for a in Article.query(status="published").all():
            print(f"  [{a.id}] {a.title}")

        print("\n=== 2. 复杂查询 (多条件) ===")
        rows = (
            Article.query(status="published")
            .where(F(Article).author_id.eq(ids["author_us"]))
            .all()
        )
        print(f"  published by Alice (US): {len(rows)} row(s)")

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

        print("\n=== 7. BaseSchema 时间戳 ===")
        art = Article.get(title="entpy SQL guide")
        print(f"  article id={art.id}")
        print(f"  create_time={art.create_time} delete_time={art.delete_time}")

        print("\n=== 8. ActiveEntity 脏字段 save() ===")
        draft = Article.get(title="Draft notes")
        draft.status = "published"
        draft.save()
        assert Article.get(title="Draft notes").status == "published"

        print("\n=== 9. edit() 显式更新 ===")
        art.edit().set("body", art.body + " (updated)").save()

        print("\n=== 10. 删除（触发 on_delete）===")
        draft_art = Article.get(title="Gremlin overview")
        to_remove = Comment.query(article_id=draft_art.id).first()
        if to_remove is not None:
            to_remove.delete()

        print_observer_events()


if __name__ == "__main__":
    main()
