# Demo 1：关系数据库（SQL）

## 概述

使用 **`with demo_bind(...):`**（连接钩子 + `config/sqlite-memory.json`）+ ActiveSchema API 演示：

- 简单 / 复杂条件查询
- EntQL
- 子表 FK 查询
- 跨表 IN 查询
- **ActiveEntity** 脏字段 `save()`、`edit().set(...).save()`

业务 API 速查见 [docs/QUICKSTART.md](../../../docs/QUICKSTART.md)。

## 运行

在仓库根目录 `ent-python/`：

```bash
python -m examples.demos.relational.demo
```

## 标准模板

```python
from entpy.active import migrate, F
from examples.demos.common.connect import demo_bind
from examples.demos.relational.models import Article, Author, Comment, SCHEMAS
from examples.demos.relational.seed import seed

with demo_bind(SCHEMAS):
    migrate()
    ids = seed()

    # 简单查询
    for a in Article.query(status="published").all():
        print(a.title)

    # 复杂查询（author_id 为 UUID，与 Author.id 一致）
    rows = (
        Article.query(status="published")
        .where(F(Article).author_id.eq(ids["author_us"]))
        .all()
    )

    # 单条
    art = Article.get(title="entpy SQL guide")

    # 子表
    comments = Comment.query(article_id=art.id).all()

    # 子表 + 复杂条件
    good = (
        Comment.query(article_id=art.id)
        .where(F(Comment).rating.gt(4))
        .all()
    )

    # EntQL
    Article.query().entql({"status": "published"}).all()

    # 跨表
    us_ids = [a.id for a in Author.query(region="US").all()]
    Article.query(status="published").where(
        F(Article).author_id.in_(us_ids)
    ).all()
```

## 字段更新（无图边）

本 demo 模型仅 FK，无边遍历；更新字段推荐：

```python
draft = Article.get(title="Draft notes")
draft.status = "published"   # 脏字段检测
draft.save()

art = Article.get(title="entpy SQL guide")
art.edit().set("body", art.body + " (updated)").save()
```

## API 速查

| 操作 | Active API |
|------|------------|
| 建表 | `migrate()` |
| 插入 | `Article.create(...)` |
| 未保存实例 | `Article.new(...)` → `.save()` |
| 等值查询 | `Article.query(status="published")` |
| 复杂条件 | `.where(F(Article).field.op(val))` |
| 单条 | `Article.get(title="...")` 或 `Article.get(id=uuid)` |
| 谓词 | `F(Schema).field.eq / gt / in_` |
| 脏字段更新 | `row.field = ...; row.save()` |
| 显式更新 | `row.edit().set("field", val).save()` |

## 数据模型

所有实体继承 `BaseSchema`（`id` UUID、`create_time`、`delete_time` 可选）：

| 表 | 关键字段 |
|----|----------|
| `authors` | id, create_time, name, region |
| `articles` | id, create_time, title, body, status, **author_id** (UUID FK) |
| `comments` | id, create_time, body, rating, **article_id** (UUID FK) |

## 相关测试

- `tests/active/test_active_entity.py`
- `tests/test_bugs.py`
