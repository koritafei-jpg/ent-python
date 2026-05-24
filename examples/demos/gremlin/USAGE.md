# Demo 5：图数据库（Gremlin）

## 概述

演示 `storage="gremlin"` 时：

- 顶点条件查询（Person / Post / Comment）
- 边遍历 `entity.out("knows")` / 属性 `.knows`
- **`link()`** 追加边（种子数据与运行时演示）
- **`with_("knows")`** 预加载后边变更与属性访问一致
- FK 子表（`Post.author_id`, `Comment.post_id`）
- **多跳**：`alice.out("knows").out("knows").all()` 链式 API

业务 API 见 [docs/QUICKSTART.md](../../../docs/QUICKSTART.md)。

## 前置条件

在仓库根目录 `ent-python/`：

```bash
docker compose -f docker-compose.gremlin.yml up -d
pip install -e ".[gremlin]"
export ENTPY_DSN="ws://localhost:8182/gremlin"  # 或 ENTPY_GREMLIN_URL；覆盖 config/gremlin-local.json
python -m examples.demos.gremlin.demo
```

无 Gremlin Server 时 demo 会打印 Skip 并退出 0。

## 数据模型

顶点继承 `BaseSchema`：`id`（UUID 属性）、`create_time`、`delete_time`（可选）。Gremlin 存储下 `Entity.id` 为图顶点 id；属性 FK 使用 UUID 类型字段。

| 顶点 | 字段 | 边 / FK |
|------|------|---------|
| `persons` | id, create_time, name, city | `person_knows` → Person |
| `posts` | title, topic, **author_id** (UUID) | — |
| `comments` | text, **post_id** (UUID) | — |

## 初始化

```python
from entpy.active import F, clear_graph, ensure_connection
from examples.demos.common.connect import demo_bind_gremlin, gremlin_config
from examples.demos.gremlin.models import Person, Post, GREMLIN_SCHEMAS
from examples.demos.gremlin.seed import seed

with demo_bind_gremlin(GREMLIN_SCHEMAS, config=gremlin_config()):
    ensure_connection()
    clear_graph("persons", "posts", "comments")
    seed()  # Gremlin 无 migrate()；种子用 alice.link("knows", bob.id)
    ...
```

## 1. 图顶点查询

```python
people = Person.query(city="NYC").all()
```

## 2. 一跳边遍历

```python
alice = Person.get(name="Alice")
friends = alice.out("knows").all()
names = alice.out("knows").values("name").all()
```

边标签规则：`{owner}_{edge_name}` → `person_knows`。

## 3. 追加边（link）

```python
dave = Person.create(name="Dave", city="NYC")
alice.link("knows", dave.id)   # 等价于 update(Person, alice.id).add("knows", dave.id).save()
```

`link()` 返回 `self`，可链式调用。

## 4. with_() 预加载与边变更

```python
row = Person.query(id=alice.id).with_("knows").only()
eve = Person.create(name="Eve", city="SF")
row.link("knows", eve.id)
# link 后 _edges 缓存失效；.knows 与 .out("knows") 一致
print([p.name for p in row.knows])
print(row.out("knows").values("name").all())
```

## 5. 子表（属性 FK）

```python
posts = Post.query(author_id=alice.id).all()
comments = Comment.query(post_id=post.id).all()
```

## 6. 多跳链式遍历

```python
alice = Person.get(name="Alice")

alice.out("knows").all()
names = alice.out("knows").values("name").all()
fof = alice.out("knows").out("knows").values("name").all()
friend_ids = alice.out("knows").ids()
```

Gremlin 存储下 2 跳及以上且无 `where` 时走服务端一次 `out` 链；SQL 存储逐跳展开。

## 7. 复合多跳（拓扑 + 属性过滤）

```python
alice = Person.get(name="Alice")
friend_ids = alice.out("knows").ids()
posts = Post.query().where(F(Post).author_id.in_(friend_ids)).all()
```

三跳示例（demo 第 8 节）：NYC 用户 → knows → 好友 → 其 posts → comments。

## 8. 显式 update（可选）

仍可使用底层 Builder：

```python
from entpy.active import update

update(Person, alice.id).add("knows", bob.id).save()
```

业务代码更推荐 `alice.link("knows", bob.id)`。

## 异步 Gremlin

```python
from entpy.active import async_bind, get_async_client
from examples.demos.common.connect import gremlin_config

cfg = gremlin_config()
async with async_bind(config=cfg, schemas=GREMLIN_SCHEMAS):
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
