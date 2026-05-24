# entpy 能力演示（Demos）

本目录包含 5 类可运行示例，展示 entpy 在关系库、全文/向量检索与图存储上的用法。所有 demo 统一使用 **`with bind(...):`** + **ActiveSchema**，业务代码无需显式 `Client.open()`。

## 目录结构

```
examples/demos/
├── README.md                 # 本说明
├── common/
│   ├── search_helpers.py     # 检索命中 + SQL 等值条件后过滤
│   └── observer_log.py       # Observer 事件记录（工具，非模型）
├── relational/               # 演示 1：SQL CRUD / 复杂查询 / FK 子表
│   ├── models/               # Author / Article / Comment
│   ├── observers/
│   ├── seed.py
│   └── demo.py
├── bm25/                     # 演示 2：BM25 全文检索
│   ├── models/               # Document / Section
│   ├── observers/
│   ├── seed.py
│   └── demo.py
├── semantic/                 # 演示 3：语义向量检索
│   ├── models/
│   ├── observers/
│   ├── seed.py
│   └── demo.py
├── hybrid/                   # 演示 4：BM25 + 语义混合（RRF）
│   ├── models/
│   ├── observers/
│   ├── seed.py
│   └── demo.py
└── gremlin/                  # 演示 5：图查询 / 多跳遍历
    ├── models/               # Person / Post / Comment
    ├── observers/
    ├── seed.py
    └── demo.py
```

## 环境

在 `python` 目录下安装依赖后运行：

```bash
cd python
pip install -e ".[dev,search,gremlin]"
```

| 演示 | 存储 | 外部依赖 |
|------|------|----------|
| 1–4 | SQLite 内存库 | 无 |
| 5 | Gremlin | Gremlin Server（默认 `ws://localhost:8182/gremlin`） |

Gremlin 演示启动方式：

```bash
docker compose -f docker-compose.gremlin.yml up -d
export ENTPY_GREMLIN_URL="ws://localhost:8182/gremlin"   # 可选
python -m examples.demos.gremlin.demo
```

无 Gremlin 服务时 demo 5 会打印 Skip 并以退出码 0 结束。

## 通用 API 模板

```python
from entpy.active import bind, migrate, F, search, traverse, update

with bind("sqlite:///:memory:", schemas=SCHEMAS):
    migrate()                          # SQL 建表；Gremlin 为 no-op
    row = User.create(name="Alice")    # 插入
    rows = User.query(status="ok").all()           # 等值查询
    one = User.get(name="Alice")                   # 单条
    rows = User.query().where(F(User).age.gt(18)).all()  # 复杂条件
    sb = search(Document)                          # 检索
    hits = sb.bm25_sync("query", top_k=5)
    friends = user.out("knows").all()              # 边 / 多跳
```

实体需继承 **`BaseSchema`**（通用字段）+ **`ActiveSchema`**（`bind` 上下文 API）：

```python
class User(ActiveSchema, BaseSchema):
    ...
```

`BaseSchema` 自动提供：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键，`uuid4` 默认生成 |
| `create_time` | time | UTC 创建时间，不可变 |
| `delete_time` | time? | 软删除时间，可选 |

外键字段（如 `author_id`、`document_id`）类型为 **UUID**，与主键一致。

### 共享模块

| 模块 | 作用 |
|------|------|
| `{demo}/models/` | 各子 demo 独立模型（每类一文件） |
| `{demo}/observers/` | 各子 demo 独立 Observer（`on_save` / `on_delete`） |
| `{demo}/seed.py` | 各子 demo 种子数据 |
| `common/search_helpers.py` | `filter_hits(schema, hits, category=..., lang=...)` 对检索结果做 SQL 后过滤 |

每个子 demo 的 `models/` 与 `observers/` 并列，由 `bind()` 按包路径自动发现 Observer，**模型无需 import Observer**。

### 边遍历 vs FK 子表

- **边 + `.out()`**：Gremlin 演示中 `Person.knows` 为图边，多跳如 `alice.out("knows").out("knows").all()`；SQL 场景下 User/Car 等亦可用 `with_()` / `entity.out()`。
- **显式 FK 子表**：relational 的 `Comment.article_id`、search 的 `Section.document_id`，便于演示子表条件查询。

---

## 演示 1：关系数据库（SQL）

**运行：** `python -m examples.demos.relational.demo`

**模型：** `Author` → `Article`（`author_id`）→ `Comment`（`article_id`）

**覆盖能力：** 简单查询、谓词 `F()`、EntQL、子表查询、跨表 `IN` 过滤

```python
from entpy.active import bind, migrate, F
from examples.demos.relational.models import Article, Author, Comment, SCHEMAS
from examples.demos.relational.seed import seed

with bind("sqlite:///:memory:", schemas=SCHEMAS):
    migrate()
    seed()

    Article.query(status="published").all()

    ids = seed()
    Article.query(status="published").where(F(Article).author_id.eq(ids["author_us"])).all()

    Article.query().entql({"status": "published"}).all()

    art = Article.get(title="entpy SQL guide")
    Comment.query(article_id=art.id).where(F(Comment).rating.gt(4)).all()

    us_ids = [a.id for a in Author.query(region="US").all()]
    Article.query(status="published").where(F(Article).author_id.in_(us_ids)).all()
```

---

## 演示 2：BM25 全文检索

**运行：** `python -m examples.demos.bm25.demo`

**说明：** SQLite 上 `postgres_ts` 后端降级为 `LIKE`；PostgreSQL 使用 `ts_rank`。

```python
from entpy.active import bind, migrate, search
from examples.demos.common.search_helpers import filter_hits
from examples.demos.bm25.models import Document, Section, SEARCH_SCHEMAS
from examples.demos.bm25.seed import seed

with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
    migrate()
    seed()
    sb = search(Document)

    hits = sb.bm25_sync("entpy runtime", top_k=5)

    raw = sb.bm25_sync("entpy runtime graph", top_k=10)
    filter_hits(Document, raw, category="tech", lang="en")

    doc = Document.get(id=hits[0].id)
    Section.query(document_id=doc.id).all()
```

---

## 演示 3：语义（向量）检索

**运行：** `python -m examples.demos.semantic.demo`

**说明：** `seed()` 返回 `MockEmbedder`；SQLite 上为暴力余弦相似度，PostgreSQL + pgvector 可走向量索引。

```python
from entpy.active import bind, migrate, search
from examples.demos.common.search_helpers import filter_hits
from examples.demos.semantic.models import Document, SEARCH_SCHEMAS
from examples.demos.semantic.seed import seed

with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
    migrate()
    emb = seed()
    sb = search(Document)

    sb.semantic_sync("vector database embedding", embedder=emb, top_k=5)

    raw = sb.semantic_sync("graph traversal", embedder=emb, top_k=10)
    filter_hits(Document, raw, lang="en", category="tech")
```

---

## 演示 4：混合检索（RRF）

**运行：** `python -m examples.demos.hybrid.demo`

**说明：** 同时跑 BM25 与语义两路，用倒数排名融合（RRF）合并；`ScoredHit.source` 为 `"hybrid"`。

```python
from entpy.active import bind, migrate, search
from examples.demos.common.search_helpers import filter_hits
from examples.demos.hybrid.models import Document, SEARCH_SCHEMAS
from examples.demos.hybrid.seed import seed

with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
    migrate()
    emb = seed()
    sb = search(Document)

    sb.hybrid_sync("pgvector entpy runtime", embedder=emb, top_k=5)

    raw = sb.hybrid_sync("vector ORM", embedder=emb, top_k=12, rrf_k=60)
    filtered = filter_hits(Document, raw, category="tech")
    top5 = sorted(filtered, key=lambda h: h.score, reverse=True)[:5]
```

---

## 演示 5：图数据库（Gremlin）

**运行：** `python -m examples.demos.gremlin.demo`

**模型：**

| 顶点标签 | 字段 | 关系 |
|----------|------|------|
| `persons` | id (UUID), name, city, create_time, delete_time | `person_knows` → Person |
| `posts` | title, topic, **author_id** (UUID) | FK 指向 Person |
| `comments` | text, **post_id** (UUID) | FK 指向 Post |

边标签规则：`{owner}_{edge_name}`，例如 `person_knows`。

```python
from entpy.active import bind, F, traverse, clear_graph, ensure_connection
from examples.demos.gremlin.models import Comment, Person, Post, GREMLIN_SCHEMAS
from examples.demos.gremlin.seed import seed

with bind("ws://localhost:8182/gremlin", schemas=GREMLIN_SCHEMAS, storage="gremlin"):
    ensure_connection()
    clear_graph("persons", "posts", "comments")
    seed()

    Person.query(city="NYC").all()

    alice = Person.get(name="Alice")
    alice.out("knows").all()                                    # 单跳
    alice.out("knows").values("name").all()                     # 多跳 + 投影
    alice.out("knows").out("knows").values("name").all()        # 两跳

    friend_ids = alice.out("knows").ids()
    Post.query().where(F(Post).author_id.in_(friend_ids)).all()
```

Gremlin 存储不支持 `migrate()`、BM25/向量检索；多跳 2 跳及以上且无 `where` 时在服务端一次 `out` 链执行。

---

## 快速运行全部（1–4）

```bash
python -m examples.demos.relational.demo
python -m examples.demos.bm25.demo
python -m examples.demos.semantic.demo
python -m examples.demos.hybrid.demo
```
