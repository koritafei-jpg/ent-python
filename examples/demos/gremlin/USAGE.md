# Demo 5：图数据库（Gremlin）

## 概述

演示 `storage="gremlin"` 时：

- 顶点条件查询（Person / Post / Comment）
- 边遍历 `traverse` / `knows`
- FK 子表（`Post.author_id`, `Comment.post_id`）
- **多跳**：`traverse().out().out()` 链式 API

## 前置条件

```bash
cd python
docker compose -f docker-compose.gremlin.yml up -d
pip install -e ".[gremlin]"
export ENTPY_GREMLIN_URL="ws://localhost:8182/gremlin"  # 可选
python -m examples.demos.gremlin.demo
```

无 Gremlin Server 时 demo 会打印 Skip 并退出 0。

## 数据模型

| 顶点 | 字段 | 边 / FK |
|------|------|---------|
| `persons` | name, city | `person_knows` → Person |
| `posts` | title, topic, **author_id** | — |
| `comments` | text, **post_id** | — |

## 初始化

```python
from entpy.active import bind, F, traverse, clear_graph, ensure_connection
from examples.demos.gremlin.schemas import Person, Post, GREMLIN_SCHEMAS
from examples.demos.gremlin.seed import seed

with bind("ws://localhost:8182/gremlin", schemas=GREMLIN_SCHEMAS, storage="gremlin"):
    ensure_connection()
    clear_graph("persons", "posts", "comments")
    seed()  # Gremlin 无 migrate()
    ...
```

## 1. 图顶点查询

```python
people = Person.query(city="NYC").all()
```

## 2. 一跳边遍历

```python
alice = Person.get(name="Alice")
friends = traverse(alice, "knows").all()
```

边标签规则：`{owner}_{edge_name}` → `person_knows`。

## 3. 子表（属性 FK）

```python
posts = Post.query(author_id=alice.id).all()
comments = Comment.query(post_id=post.id).all()
```

## 4. 多跳链式遍历

```python
alice = Person.get(name="Alice")

# 一跳（两种写法等价）
traverse(alice, "knows").all()
traverse(alice).out("knows").all()

# 多跳 + 字段投影
names = traverse(alice).out("knows").values("name").all()
fof = traverse(alice).out("knows").out("knows").values("name").all()

# 多跳后取 id，再查子表
friend_ids = traverse(alice).out("knows").ids()
```

Gremlin 存储下 2 跳及以上且无 `where` 时走服务端一次 `out` 链；SQL 存储逐跳展开。

## 5. 复合多跳（拓扑 + 属性过滤）

```python
alice = Person.get(name="Alice")
friend_ids = traverse(alice).out("knows").ids()
posts = Post.query().where(F(Post).author_id.in_(friend_ids)).all()
```

三跳示例（demo 第 8 节）：NYC 用户 → knows → 好友 → 其 posts → comments。

## 异步 Gremlin

```python
from entpy.active import async_bind, get_async_client

async with async_bind(url, schemas=GREMLIN_SCHEMAS, storage="gremlin"):
    u = await get_async_client().create(Person, name="X", city="NYC").save()
```

## 限制（与 ent 一致）

| 能力 | Gremlin |
|------|---------|
| `migrate()` | 无 |
| BM25 / 向量检索 | 不支持 |
| 事务 | NopTx |

## 相关测试

- `tests/integration/test_gremlin_runtime.py`
- `tests/active/test_traverse_chain.py`
