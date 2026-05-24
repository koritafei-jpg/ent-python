# entpy 快速入门（降低学习曲线）

面向业务开发：先会用 **Active API**，再按需看 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 1. 心智模型（3 分钟）

```
Schema 类（字段 + 边）
    ↓ bind() 绑定数据库
ActiveSchema：User.create / User.query / entity.save
    ↓ 底层
Client + SQL 或 Gremlin
```

- **一张表 / 一个顶点** = 一个 `class User(ActiveSchema, BaseSchema)`
- **主键** 默认 UUID（`BaseSchema`），不是自增 int
- **所有 ORM 操作** 写在 `with bind(...):` 或 `async with async_bind(...):` 里

## 2. 最小可运行示例

```python
from entpy.active import bind, migrate, F
from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, field

class User(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [field.string("name"), field.int_("age")]

SCHEMAS = [User]

with bind("sqlite:///:memory:", schemas=SCHEMAS):
    migrate()
    u = User.create(name="Alice", age=30)
    u.age = 31
    u.save()                                    # 只提交改过的字段
    adults = User.query().where(F(User).age.gt(18)).all()
```

## 3. 常用操作速查

| 你想做的事 | 推荐写法 |
|------------|----------|
| 插入 | `User.create(name="a", age=1)` |
| 先改再存 | `u = User.new(...); u.save()` |
| 按条件查 | `User.query(name="a").all()` 或 `.where(F(User).age.gt(1))` |
| 单条 | `User.get(id=uuid)` |
| 改字段 | `u.name = "x"; u.save()` |
| 改边（追加） | `u.link("groups", group_id)` 或 `u.edit().add("groups", gid).save()` |
| M2M 边整表替换 | `u.set_links("groups", g1, g2)` 或 `u.edit().set_edges("groups", g1).save()` |
| 删行 | `u.delete()` |
| 走边 | `u.out("groups").all()` |
| 多跳 | `u.out("knows").out("knows").all()` |
| JSON 过滤 | `User.query().entql({"age": {"gt": 18}}).all()` |
| 预加载边 | `User.query().with_("groups").all()` 后访问 `row.groups` |

## 4. 边（关系）语义

| API | 适用 | 行为 |
|-----|------|------|
| `add(edge, *ids)` | M2M / O2M 等 | **追加**，重复 id 幂等 |
| `set_edges(edge, *ids)` | 仅 M2M | **全量替换**；`set_edges("groups")` 清空 |
| `link` / `set_links` | ActiveEntity 快捷方式 | 同上，一行保存 |

声明边在 Schema 的 `edges()` 里，用 `to("cars", Car)` / `from_("groups", Group)`。

## 5. 同步 vs 异步

| | 同步 | 异步 |
|---|------|------|
| 上下文 | `with bind(dsn, schemas=...):` | `async with async_bind(dsn, schemas=...):` |
| 建表 | `migrate()` | `await migrate_async()` |
| 实体保存 | `u.save()` | `await u.persist()` |
| 实体删 | `u.delete()` | `await u.discard()` |
| 更新构建器 | `u.edit().set(...).save()` | `await u.edit().set(...).save()` |
| 遍历 | `u.out("e").all()` | `await u.out("e").all()` |

**不要**在 `async_bind` 里用 `User.create()` / 模块级 `update()` — 用 `get_async_client()` 或 `await u.edit()...`。

## 6. 何时用 Client API

需要连接池、多 schema 显式切换、或无 `bind` 上下文时：

```python
client = Client.open(dsn, schemas=SCHEMAS)
client.migrate()
client.create(User, name="a", age=1).save()
client.update(User, user_id).add("groups", g_id).save()
```

Active API 底层即 Client，二者语义一致。

## 7. 常见错误

| 现象 | 原因 |
|------|------|
| `no active entpy bind` | 未进入 `with bind(...)` |
| `ActiveSchema 同步 API 需要 bind` | 在 `async_bind` 里调了 `User.create()` |
| `unknown edge` / `unknown field` | 边名或字段名拼写错误（**调用时**即报错） |
| `not found` | `get` / `only` / `update` 的 id 不存在 |
| 遍历结果与库不一致（逆 FK） | 单跳逆 FK 以**数据库**为准，勿只改内存 FK |

## 8. 下一步

- 入门示例：`examples/start/`
- 五类能力演示：`examples/demos/README.md`
- 架构与性能细节：[ARCHITECTURE.md](ARCHITECTURE.md)
