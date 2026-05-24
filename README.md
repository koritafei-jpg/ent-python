# entpy

Python 实体框架：用 Schema 类描述数据模型，运行时直接 CRUD / 查询 / 检索，**无需代码生成**。支持 SQL（SQLAlchemy 2.x）与 Gremlin 图存储，可选 BM25 + 向量混合检索。

## 包结构

```
python/
├── entpy/                      # 主库
│   ├── active/                 # bind() 上下文 + ActiveSchema（推荐业务入口）
│   ├── schema/                 # Schema / Field / Edge DSL
│   ├── ir/                     # Schema → 图 IR（表、边、join）
│   ├── runtime/                # Client、构建器、traverse、hooks
│   ├── dialect/
│   │   ├── sqlalchemy/         # SQL 驱动、sqlgraph、迁移、pgvector 类型
│   │   └── gremlin/            # Gremlin 驱动与图 CRUD
│   ├── entql/                  # JSON 风格查询过滤器
│   ├── privacy/                # 访问策略 Allow / Deny / Skip
│   ├── search/                 # BM25、语义、混合 RRF、reindex
│   ├── codegen/                # 可选 .pyi 桩与薄封装生成
│   └── cli/                    # entpy 命令行
├── examples/
│   └── demos/                  # 五类能力演示（见下文）
├── tests/                      # 单元与集成测试
├── docker-compose.gremlin.yml  # Gremlin Server（演示 5）
└── docker-compose.pgvector.yml # PostgreSQL + pgvector（集成测试）
```

### 分层说明

| 层 | 职责 |
|----|------|
| `schema` | 声明字段、边、索引、检索配置、hooks |
| `ir` | 将 Schema 解析为表名、FK、M2M join、Gremlin 标签 |
| `runtime` | `Client` / 构建器执行增删改查与边遍历 |
| `active` | `bind()` 绑定连接；`User.create()` / `User.query()` 无需显式 Client |
| `dialect` | 对接 SQLite / PostgreSQL / Gremlin |
| `search` | 检索注册表、`SearchBuilder`、可插拔 BM25 后端 |

## 安装与测试

```bash
cd python
pip install -e ".[dev,async,search,codegen,gremlin]"
pytest -q
```

## 快速开始（bind API）

```python
from entpy.active import bind, migrate, F
from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field

class User(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [field.string("name"), field.int_("age")]
        # id (UUID)、create_time、delete_time 由 BaseSchema 提供

SCHEMAS = [User]

with bind("sqlite:///:memory:", schemas=SCHEMAS):
    migrate()
    alice = User.create(name="Alice", age=30)
    users = User.query(name="Alice").all()
    bob = User.new(name="Bob", age=25)
    bob.save()
    adults = User.query().where(F(User).age.gt(18)).all()
```

### 显式 Client（底层 API）

```python
from entpy.runtime import Client, F

client = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
client.migrate()
user = client.create(User, name="Alice", age=30).save()
users = client.query(User).where(F(User).name.eq("Alice")).all()
```

### 常用 API 对照

| 操作 | Active API | Client API |
|------|------------|------------|
| 建表 | `migrate()` | `client.migrate()` |
| 插入 | `User.create(...)` | `client.create(User, ...).save()` |
| 查询 | `User.query(...).where(F(User)...)` | `client.query(User).where(...)` |
| 单条 | `User.get(id=uuid)` | `.only()` |
| 检索 | `search(Document).bm25_sync(...)` | `client.search(Document)...` |
| 边遍历 | `traverse(e).out("knows").all()` | `client.traverse(e, "knows").all()` |
| 更新边 | `update(Person, id).add("knows", peer_id).save()` | 同左 |

### Observer（自动注册，Schema 零依赖）

将 `UserObserver` 放在与 Schema 同级的 `observers` 包（如 `examples/start/observers/user.py`），`bind()` / `Client.open()` 会按命名约定自动发现并挂接 Hook，**无需在 Schema 中 import Observer**。

```python
from entpy.observer import Observer

class UserObserver(Observer):
    def creating(self, mutation):
        mutation.fields["name"] = mutation.fields["name"].strip()

    def on_save(self, mutation):
        ...  # CREATE / UPDATE 持久化后，mutation.id 已赋值

    def on_delete(self, mutation):
        ...  # DELETE 成功后
```

也可显式绑定：`@observes(User)`。自定义扫描包：`bind(..., observer_packages=["myapp.observers"])`.

### 异步

```python
from entpy.active import async_bind, migrate_async, get_async_client

async with async_bind("sqlite+aiosqlite:///:memory:", schemas=SCHEMAS):
    await migrate_async()
    client = get_async_client()
    user = await client.create(User, name="Alice", age=30).save()
```

### 检索

```python
from entpy.active import bind, migrate, search
from entpy.search import MockEmbedder

with bind(dsn, schemas=SCHEMAS):
    migrate()
    emb = MockEmbedder(dim=8)
    sb = search(Document)
    sb.bm25_sync("关键词", top_k=10)
    sb.semantic_sync("查询句", embedder=emb, top_k=10)
    sb.hybrid_sync("查询句", embedder=emb, top_k=10, rrf_k=60)
```

### Gremlin

```python
from entpy.active import bind, traverse, clear_graph, ensure_connection

with bind("ws://localhost:8182/gremlin", schemas=SCHEMAS, storage="gremlin"):
    ensure_connection()
    clear_graph("persons", "posts")
    person = Person.create(name="Alice", city="NYC")
    traverse(person).out("knows").out("knows").values("name").all()
```

## 能力演示（examples/demos）

五类 demo 均在 `examples/demos/`，使用 `bind()` + `ActiveSchema` + `BaseSchema`（UUID 主键与时间戳），可直接运行：

| # | 命令 | 场景 |
|---|------|------|
| 1 | `python -m examples.demos.relational.demo` | SQL CRUD、复杂查询、FK 子表 |
| 2 | `python -m examples.demos.bm25.demo` | BM25 全文检索 + 条件过滤 |
| 3 | `python -m examples.demos.semantic.demo` | 语义向量检索 |
| 4 | `python -m examples.demos.hybrid.demo` | BM25 + 语义 RRF 混合 |
| 5 | `python -m examples.demos.gremlin.demo` | 图顶点、边遍历、多跳链 |

演示 1–4 使用 SQLite 内存库；演示 5 需先启动 Gremlin：

```bash
docker compose -f docker-compose.gremlin.yml up -d
python -m examples.demos.gremlin.demo
```

### 演示 1 示例（关系库）

```python
from entpy.active import bind, migrate, F
from examples.demos.relational.models import Article, Comment, SCHEMAS
from examples.demos.relational.seed import seed

with bind("sqlite:///:memory:", schemas=SCHEMAS):
    migrate()
    seed()
    Article.query(status="published").all()
    art = Article.get(title="entpy SQL guide")
    Comment.query(article_id=art.id).where(F(Comment).rating.gt(4)).all()
```

### 演示 2–4 示例（检索）

```python
from entpy.active import bind, migrate, search
from examples.demos.common.search_helpers import filter_hits
from examples.demos.bm25.models import Document, SEARCH_SCHEMAS
from examples.demos.bm25.seed import seed

with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
    migrate()
    emb = seed()
    sb = search(Document)
    sb.bm25_sync("entpy runtime", top_k=5)
    sb.semantic_sync("vector search", embedder=emb, top_k=5)
    sb.hybrid_sync("entpy graph", embedder=emb, top_k=5)
    filter_hits(Document, sb.bm25_sync("search", top_k=10), category="tech")
```

### 演示 5 示例（多跳图遍历）

```python
from entpy.active import bind, traverse, clear_graph, ensure_connection
from examples.demos.gremlin.models import Person, GREMLIN_SCHEMAS
from examples.demos.gremlin.seed import seed

with bind("ws://localhost:8182/gremlin", schemas=GREMLIN_SCHEMAS, storage="gremlin"):
    ensure_connection()
    clear_graph("persons", "posts", "comments")
    seed()
    alice = Person.get(name="Alice")
    traverse(alice).out("knows").values("name").all()
    traverse(alice).out("knows").out("knows").values("name").all()
```

## CLI

```bash
entpy stubs generate myapp.schemas --target entpy_stubs
entpy generate thin myapp.schemas --target ent_generated
entpy search reindex myapp.schemas --schema Document --dsn sqlite:///:memory: --embedder mock
```
