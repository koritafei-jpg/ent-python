# entpy 能力演示（Demos）

本目录包含 5 类可运行示例，展示 entpy 在关系库、全文/向量检索与图存储上的用法。所有 demo 统一通过 **`demo_bind` / `demo_bind_gremlin`**（连接钩子 + JSON 配置）绑定 **ActiveSchema**，业务代码无需显式 `Client.open()` 或硬编码 DSN。

**推荐先读** [docs/QUICKSTART.md](../../docs/QUICKSTART.md)（心智模型、边语义、`edit` / `link` / `set_links`）。各子目录另有 `USAGE.md`。

## 目录结构

```
examples/demos/
├── README.md                 # 本说明
├── config/
│   ├── sqlite-memory.json    # SQL demo 连接（ConfigConnectionHook）
│   └── gremlin-local.json
├── common/
│   ├── connect.py            # demo_bind / demo_bind_gremlin
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

在仓库根目录 `ent-python/` 安装依赖后运行：

```bash
pip install -e ".[dev,search,gremlin]"
```

| 演示 | 存储 | 外部依赖 |
|------|------|----------|
| 1–4 | SQLite 内存库 | 无 |
| 5 | Gremlin | Gremlin Server（默认见 `config/gremlin-local.json`） |

### 连接钩子（demo 默认）

各 `demo.py` 通过 `examples.demos.common.connect` 调用 `bind(config=...)`，由内置 **`ConfigConnectionHook`** 解析 JSON，而非硬编码 DSN。

| 方式 | 用法 |
|------|------|
| 默认 | `with demo_bind(SCHEMAS):` → `config/sqlite-memory.json` |
| 环境变量 | `ENTPY_DEMO_SOURCE=env` + `ENTPY_DSN=...`（`EnvConnectionHook`） |
| 自定义钩子 | `register_demo_connection_hook(match_fn, open_fn)` |

Gremlin 演示启动方式：

```bash
docker compose -f docker-compose.gremlin.yml up -d
export ENTPY_DSN="ws://localhost:8182/gremlin"   # 或 ENTPY_GREMLIN_URL
python -m examples.demos.gremlin.demo
```

无 Gremlin 服务时 demo 5 会打印 Skip 并以退出码 0 结束。

## 通用 API 模板

```python
from entpy.active import migrate, F, search
from examples.demos.common.connect import demo_bind

with demo_bind(SCHEMAS):
    migrate()                          # SQL 建表；Gremlin 为 no-op
    row = User.create(name="Alice")    # 插入
    rows = User.query(status="ok").all()           # 等值查询
    one = User.get(name="Alice")                   # 单条
    rows = User.query().where(F(User).age.gt(18)).all()  # 复杂条件
    row.field = "x"; row.save()                    # 脏字段更新
    row.edit().set("field", "y").save()            # 显式更新
    user.link("knows", friend_id)                  # 追加边（Gremlin / 有边 Schema）
    sb = search(Document)                          # 检索
    hits = sb.bm25_sync("query", top_k=5)
    friends = user.out("knows").all()              # 边 / 多跳
```

| 写操作 | 说明 |
|--------|------|
| `row.save()` | 仅提交脏字段 |
| `row.edit().set(...).save()` | 显式字段更新 Builder |
| `row.link(edge, *ids)` | 追加边（M2M 幂等；O2M 绑定 FK） |
| `row.set_links(edge, *ids)` | 仅 M2M：保存后边集合恰好为给定 id |
| `User.query(...).with_("edge").only()` | 预加载边；`link` 后缓存失效，属性边与 `out()` 一致 |

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
| `common/connect.py` | `demo_bind` / `demo_bind_gremlin`：经 `ConfigConnectionHook` 读 `config/*.json` |
| `config/sqlite-memory.json` | SQL demo 默认 DSN（内存 SQLite） |
| `config/gremlin-local.json` | Gremlin demo 默认 WebSocket URL |
| `common/search_helpers.py` | `filter_hits(schema, hits, category=..., lang=...)` 对检索结果做 SQL 后过滤 |

每个子 demo 的 `models/` 与 `observers/` 并列，由 `bind()` 按包路径自动发现 Observer，**模型无需 import Observer**。

### 边遍历 vs FK 子表

- **边 + `.out()`**：Gremlin 演示中 `Person.knows` 为图边，多跳如 `alice.out("knows").out("knows").all()`；SQL 场景下 User/Car 等亦可用 `with_()` / `entity.out()`。
- **显式 FK 子表**：relational 的 `Comment.article_id`、search 的 `Section.document_id`，便于演示子表条件查询。

---

## 演示 1：关系数据库（SQL）

**运行：** `python -m examples.demos.relational.demo`

**模型：** `Author` → `Article`（`author_id`）→ `Comment`（`article_id`）

**覆盖能力：** 简单查询、谓词 `F()`、EntQL、子表查询、跨表 `IN` 过滤、**`save()` / `edit()` 字段更新**

```python
from entpy.active import migrate, F
from examples.demos.common.connect import demo_bind
from examples.demos.relational.models import Article, Author, Comment, SCHEMAS
from examples.demos.relational.seed import seed

with demo_bind(SCHEMAS):
    migrate()
    ids = seed()

    Article.query(status="published").all()
    Article.query(status="published").where(F(Article).author_id.eq(ids["author_us"])).all()
    Article.query().entql({"status": "published"}).all()

    art = Article.get(title="entpy SQL guide")
    Comment.query(article_id=art.id).where(F(Comment).rating.gt(4)).all()

    draft = Article.get(title="Draft notes")
    draft.status = "published"
    draft.save()
    art.edit().set("body", art.body + " (updated)").save()
```

---

## 演示 2：BM25 全文检索

**运行：** `python -m examples.demos.bm25.demo`

**说明：** SQLite 上 `postgres_ts` 后端降级为 `LIKE`；PostgreSQL 使用 `ts_rank`。

```python
from entpy.active import migrate, search
from examples.demos.common.connect import demo_bind
from examples.demos.common.search_helpers import filter_hits
from examples.demos.bm25.models import Document, Section, SEARCH_SCHEMAS
from examples.demos.bm25.seed import seed

with demo_bind(SEARCH_SCHEMAS):
    migrate()
    seed()
    sb = search(Document)

    hits = sb.bm25_sync("entpy runtime", top_k=5)

    raw = sb.bm25_sync("entpy runtime graph", top_k=10)
    filter_hits(Document, raw, category="tech", lang="en")

    doc = Document.get(id=hits[0].id)
    Section.query(document_id=doc.id).all()

    doc = Document.get(title="entpy SQL runtime")
    doc.lang = "en"
    doc.save()
```

---

## 演示 3：语义（向量）检索

**运行：** `python -m examples.demos.semantic.demo`

**说明：** `seed()` 返回 `MockEmbedder`；SQLite 上为暴力余弦相似度，PostgreSQL + pgvector 可走向量索引。

```python
from entpy.active import migrate, search
from examples.demos.common.connect import demo_bind
from examples.demos.common.search_helpers import filter_hits
from examples.demos.semantic.models import Document, SEARCH_SCHEMAS
from examples.demos.semantic.seed import seed

with demo_bind(SEARCH_SCHEMAS):
    migrate()
    emb = seed()
    sb = search(Document)

    sb.semantic_sync("vector database embedding", embedder=emb, top_k=5)

    raw = sb.semantic_sync("graph traversal", embedder=emb, top_k=10)
    filter_hits(Document, raw, lang="en", category="tech")

    doc = Document.get(title="entpy SQL runtime")
    doc.edit().set("lang", "en").save()
```

---

## 演示 4：混合检索（RRF）

**运行：** `python -m examples.demos.hybrid.demo`

**说明：** 同时跑 BM25 与语义两路，用倒数排名融合（RRF）合并；`ScoredHit.source` 为 `"hybrid"`。

```python
from entpy.active import migrate, search
from examples.demos.common.connect import demo_bind
from examples.demos.common.search_helpers import filter_hits
from examples.demos.hybrid.models import Document, SEARCH_SCHEMAS
from examples.demos.hybrid.seed import seed

with demo_bind(SEARCH_SCHEMAS):
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
from entpy.active import F, clear_graph, ensure_connection
from examples.demos.common.connect import demo_bind_gremlin
from examples.demos.gremlin.models import Comment, Person, Post, GREMLIN_SCHEMAS
from examples.demos.gremlin.seed import seed

with demo_bind_gremlin(GREMLIN_SCHEMAS):
    ensure_connection()
    clear_graph("persons", "posts", "comments")
    seed()  # alice.link("knows", bob.id)

    alice = Person.get(name="Alice")
    alice.out("knows").all()
    alice.link("knows", dave_id)

    row = Person.query(id=alice.id).with_("knows").only()
    row.link("knows", eve_id)
    row.knows  # 与 row.out("knows").all() 一致（link 后缓存失效）
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
