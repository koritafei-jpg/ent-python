# entpy 架构设计与端到端执行流程

本文档描述 entpy 的分层架构、启动编译流程、CRUD/遍历/检索的端到端路径，以及谓词如何下推为 SQL/Gremlin。

## 1. 设计目标与总体分层

entpy 是 **运行时优先（runtime-first）** 的实体框架：用 Python 类声明 Schema，启动时编译为中间表示（IR），再通过 `Client` / `ActiveSchema` 执行 CRUD、图遍历与检索。**不生成 ORM 代码**，Schema 即唯一数据源。

```
┌─────────────────────────────────────────────────────────────────┐
│  声明层 (Declarative)                                            │
│  schema/   Field、Edge、BaseSchema、SearchMixin、@hook、Policy   │
├─────────────────────────────────────────────────────────────────┤
│  编译层 (IR)                                                     │
│  ir/       Schema → NodeDescriptor → Graph（表/FK/M2M/Gremlin 标签）│
├─────────────────────────────────────────────────────────────────┤
│  注册层 (Registry)                                               │
│  runtime/registry   Graph + SQLAlchemy Table + PredicateFactory  │
├─────────────────────────────────────────────────────────────────┤
│  API 层                                                          │
│  active/   bind() + ActiveSchema（ContextVar 隐式 Client）        │
│  runtime/  Client + Builders + Predicate + Traverse            │
├─────────────────────────────────────────────────────────────────┤
│  横切能力                                                        │
│  observer/  生命周期钩子（自动发现）                              │
│  privacy/   Allow / Deny / Skip 策略链                           │
│  entql/     JSON 过滤器 → Predicate                              │
│  search/    BM25 / 向量 / RRF 混合                               │
├─────────────────────────────────────────────────────────────────┤
│  方言层 (Dialect)                                                │
│  dialect/sqlalchemy/   sqlgraph → INSERT/SELECT/UPDATE/DELETE  │
│  dialect/gremlin/      graph_ops → addV/addE/遍历                │
└─────────────────────────────────────────────────────────────────┘
```

| 层 | 目录 | 核心职责 |
|----|------|----------|
| Schema | `entpy/schema/` | DSL：字段类型、边、索引、检索配置、Mixin hooks |
| IR | `entpy/ir/` | 将 Schema 类解析为 `NodeDescriptor` 与 `Graph` |
| Registry | `entpy/runtime/registry.py` | 持有 Graph、SQL 表元数据、每 Schema 的 `F()` 工厂 |
| Runtime | `entpy/runtime/` | CRUD 构建器、谓词、遍历、Mutation |
| Active | `entpy/active/` | `bind()` 绑定 Client；`User.create()` 语法糖 |
| Observer | `entpy/observer/` | `creating` / `on_save` 等，转成 Hook 或后置回调 |
| Dialect | `entpy/dialect/` | 真正访问数据库 |

---

## 2. 启动与编译流程

`Client.open()` / `bind()` 打开连接时，**一次性**完成 Schema → 可执行结构的编译：

```mermaid
sequenceDiagram
    participant App as 应用代码
    participant Client as Client.open
    participant Reg as Registry.from_schemas
    participant IR as build_graph
    participant Meta as tables_for_graph
    participant Pol as collect_runtime_hooks

    App->>Client: schemas, storage, observer_packages
    Client->>Reg: from_schemas(schemas, storage)
    Reg->>IR: load_schemas + build_graph
    IR-->>Reg: Graph (nodes, edges, FK, M2M join)
    alt storage == sql
        Reg->>Meta: tables_for_graph(graph)
        Meta-->>Reg: dict[name, SQLAlchemy Table]
    end
    Reg-->>Client: Registry + PredicateFactory per schema
    Client->>Pol: collect_runtime_hooks + interceptors + policies
    Pol-->>Client: hooks[], observers[]
```

关键入口：`Registry.from_schemas()`（`entpy/runtime/registry.py`）：

1. `build_graph(schemas)` — 解析边、FK、M2M join 表
2. `tables_for_graph(graph)` — 仅 SQL 存储时生成 `SQLAlchemy Table`
3. 为每个 Schema 构建 `PredicateFactory`（字段名 → 列名）

**编译产物：**

- `Graph`：节点名、边类型（O2O/O2M/M2M）、FK 列、join 表
- `tables`（仅 SQL）：含 UUID 主键、`create_time` / `delete_time` 等列
- `PredicateFactory`：供 `F(User).age` 使用

---

## 3. ActiveSchema 与 Client 的关系

`ActiveSchema` **不重复实现**持久化逻辑，只是从 `ContextVar` 取出当前 `Client` 并委托给 Builder（`entpy/active/schema.py`）。

| 能力 | Active API | 底层等价 |
|------|------------|----------|
| 创建 | `User.create(name="x")` | `client.create(User, name="x").save()` |
| 查询 | `User.query(age=18)` | `client.query(User).where(F(User).age.eq(18))` |
| 谓词 | `F(User)` via `get_client().F(User)` | `client.F(User)` |
| 遍历 | `e.out("knows").out("knows")` | `client.traverse(e, "knows")` |

**约束：** `ActiveSchema` 必须在 `with bind(...):` 块内使用，否则 `get_client()` 抛错。

---

## 4. 谓词是否「转 SQL」？

**结论：会下推到数据库，但不是字符串拼接 SQL，而是编译为 SQLAlchemy 表达式 / Gremlin 遍历步骤。**

### 4.1 谓词模型

`F(User).age.gt(18)` 构建 `Predicate` 对象，内部持有两个闭包（`entpy/runtime/predicate.py`）：

- `fn(table)` → SQLAlchemy 表达式，如 `table.c.age > 18`
- `gremlin_fn(t)` → Gremlin 步骤，如 `t.has("age", P.gt(18))`

当前 `FieldRef` 支持：`eq`、`ne`、`in_`、`gt`（尚无 `lt` / `gte` / `like` 等）。

### 4.2 查询时下推路径

```
client.F(User).age.gt(18)
  → Predicate(fn, gremlin_fn)
  → QueryBuilder._run_query()
  → sql_preds = [p.apply(table) for p in preds]
  → sqlgraph.query_nodes(..., predicates=sql_preds)
  → select(table).where(pred).limit(...)
  → session.execute(stmt)   # SQLAlchemy 编译为参数化 SQL
```

Gremlin 分支对每个 `Predicate` 调用 `apply_gremlin()`，在遍历上追加 `.has()` 等步骤。

**实际 SQL 形态（由 SQLAlchemy 生成，示意）：**

```sql
SELECT users.id, users.name, users.age, ...
FROM users
WHERE users.age > :age_1
LIMIT :param_1
```

### 4.3 EntQL 路径

`QueryBuilder.entql({"age": {"gt": 18}})` → `entql_to_predicates()`（`entpy/entql/filter.py`）→ 同样生成 `Predicate`，之后与 `where()` 相同下推。

### 4.4 不会自动转 SQL 的场景

| 场景 | 行为 |
|------|------|
| 任意 Python 函数过滤 | 不支持；须用 `F()` / EntQL |
| `entity.out().where(...)` 多跳过滤 | 部分在 Python 二次 query |
| Policy / Hook / Observer | 纯 Python |
| Search 的 RRF 融合 | Python 合并排名 |
| 非 PG 环境的语义检索 | Python 暴力余弦（有 pgvector 时才下推） |

---

## 5. 端到端：CREATE

```mermaid
flowchart TD
    A[User.create / client.create.save] --> B[_validate_fields]
    B --> C[Mutation Op.CREATE]
    C --> D[chain_hooks 洋葱链]
    D --> E[eval_mutation Policy]
    E --> F[create_spec → CreateSpec]
    F --> G{storage?}
    G -->|sql| H[sqlgraph.create_node INSERT]
    G -->|gremlin| I[graph_ops.create_node addV]
    H --> J[mutation.id = row_id]
    I --> J
    J --> K[notify_after_observers on_save]
    K --> L[Entity / ActiveEntity]
```

| 步骤 | 位置 | Python / DB |
|------|------|-------------|
| 默认值、validators | `CreateBuilder._validate_fields` | **Python** |
| 修改 fields | `chain_hooks`（含 Observer `creating`） | **Python** |
| 权限检查 | `eval_mutation` | **Python** |
| 构建 INSERT spec | `create_spec()` | **Python** |
| 写库 + 边 | `sqlgraph.create_node` / `graph_ops.create_node` | **DB** |
| 后置回调 | `notify_after_observers` | **Python**（`on_save`） |

边写入（SQL）在 `create_node` 内按关系类型处理：M2M 插 join 表，O2M/O2O 更新对端 FK。

---

## 6. 端到端：QUERY

```mermaid
flowchart TD
    A[User.query / client.query.where] --> B[eval_query Policy]
    B --> C[chain_interceptors 可选]
    C --> D[Predicate.apply / apply_gremlin]
    D --> E[sqlgraph.query_nodes / graph_ops.query_nodes]
    E --> F[Entity 列表]
```

| 步骤 | Python / DB |
|------|-------------|
| `eval_query`：策略过滤/拒绝 | **Python**（在 DB 前） |
| Interceptor 包装 execute | **Python** |
| `p.apply(table)` → SQLAlchemy WHERE | **编译为 SQL** |
| `select(table).where(...).limit(...)` | **DB** |
| 结果封装为 `Entity` | **Python** |
| `with_("cars")` 预加载边 | **DB**（额外 SELECT） |

**注意：** Query **不经过** Observer；读路径无 `on_save`。

---

## 7. 端到端：UPDATE / DELETE

### UPDATE

与 CREATE 类似：`updating` Hook → Policy → `update_spec` → `UPDATE` SQL / Gremlin `property()` → `notify_after_observers`（`updated` + `on_save`）→ 再 query 一次返回最新行。

### DELETE

- 若只有 `where()` 没有 `one(id)`，会 **先在 Python 里 query 出 id 列表**，再 DELETE
- `chain_hooks` 含 `deleting`
- 成功后 `on_delete`

---

## 8. 端到端：TRAVERSE（边遍历）

入口：`entity.out("knows")` 或 `client.traverse(entity, "knows")` → `TraverseChain`（`entpy/runtime/traverse.py`）

| 模式 | 实现 | 下推程度 |
|------|------|----------|
| SQL 单跳 | `resolve_edge` → FK 谓词 → `query_nodes` | **DB** |
| Gremlin 单跳 | `graph_ops.traverse_neighbors` | **DB** |
| Gremlin 多跳无过滤 | `traverse_chain` 一次遍历 | **DB**（fast path） |
| SQL 多跳 | `all()` 循环 `_hop_neighbors` | **Python 逐跳** |
| 带 `where()` 过滤 | 收集邻居 id → 二次 `QueryBuilder` | **混合** |

图存储与关系库在遍历能力上不对等：Gremlin 多跳可一次下推，SQL 多跳目前是应用层迭代。

---

## 9. 端到端：SEARCH（检索）

```mermaid
flowchart LR
    SB[SearchBuilder] --> BM25[bm25_sync]
    SB --> SEM[semantic_sync]
    SB --> HYB[hybrid_sync]
    BM25 --> PG[Postgres tsvector / SQLite LIKE]
    SEM --> VEC[pgvector 或 Python 余弦]
    HYB --> RRF[reciprocal_rank_fusion Python]
```

| 方法 | 下推 | 说明 |
|------|------|------|
| `bm25_sync` | **DB** | PG `ts_rank` 或 SQLite `LIKE` |
| `semantic_sync` | **DB 或 Python** | 有 pgvector 用距离排序；否则全表拉取向量后 Python 算相似度 |
| `hybrid_sync` | **混合** | 两次检索 + Python RRF 融合 |
| `reindex` | **混合** | query 全表 → embed → `update().set(embedding)` |

检索与 CRUD 共用同一 `Client` 与 `Registry`，但走独立的 `SearchRegistry`（从 `SearchMixin.search_config()` 解析）。

---

## 10. Hook / Observer / Policy 执行顺序

### 10.1 Hook 列表组装（`collect_runtime_hooks`）

```
extra_hooks（Client.open_with 传入）
  + Schema/Mixin 上的 @hook
  + observers_to_hooks()（仅 creating / updating / deleting）
```

### 10.2 变更（CREATE / UPDATE / DELETE）顺序

```
1. _validate_fields()          [仅 CREATE]
2. 构建 Mutation
3. chain_hooks()               ← 洋葱链，持久化前
   └─ Observer creating/updating/deleting
   └─ Schema @hook
4. eval_mutation()             ← Policy 规则链
5. create_spec / update_spec / delete_spec
6. sqlgraph / graph_ops        ← 真正写库
7. notify_after_observers()    ← 持久化后，不在 Hook 链内
   ├─ created/updated/deleted（若子类 override）
   └─ on_save / on_delete
```

`chain_hooks` 采用洋葱模型：列表中的 Hook 从外到内包裹 `_TerminalMutator`，持久化前可修改 `mutation.fields`。

Observer **后置**方法（`created` / `updated` / `deleted` / `on_save` / `on_delete`）在 Hook 链**之外**同步调用，不参与 `chain_hooks`。

### 10.3 查询顺序

```
eval_query(Policy)  →  chain_interceptors  →  execute(SQL/Gremlin)
```

---

## 11. Python 层 vs 数据库层

| 留在 Python | 下推到 DB |
|-------------|-----------|
| 字段默认值、validators | INSERT / UPDATE / DELETE |
| Hook / Observer 修改 mutation | WHERE（Predicate → SQLAlchemy / Gremlin） |
| Policy Allow / Deny / Skip | BM25（PG / SQLite） |
| Delete 先 query 解析 id | pgvector 距离（若有） |
| SQL 多跳 traverse 逐跳 | Gremlin 多跳 fast path |
| Traverse 带 where 二次过滤 | 单跳 FK / Gremlin out |
| Hybrid RRF、非 PG 语义搜索 | |
| Entity / ActiveEntity 封装、脏字段跟踪 | |
| Interceptor 链 | |

---

## 12. 数据流总览

```mermaid
flowchart TB
    subgraph declarative [声明层]
        Schema[Schema 类定义]
    end

    subgraph compile [编译层 - 启动时一次]
        Loader[ir.loader.load_schemas]
        Graph[ir.graph.build_graph]
        Meta[metadata.tables_for_graph]
        Registry[Registry.from_schemas]
    end

    subgraph api [API 层]
        Bind[active.bind ContextVar]
        Client[Client + Builders]
        Active[ActiveSchema 薄封装]
    end

    subgraph cross [横切]
        Hooks[chain_hooks]
        Policy[eval_query / eval_mutation]
        Obs[notify_after_observers]
    end

    subgraph exec [方言层 - 每次操作]
        SQL[sqlgraph: SQLAlchemy stmt]
        Gremlin[graph_ops: Gremlin traversal]
    end

    Schema --> Loader --> Graph
    Graph --> Meta --> Registry
    Bind --> Client
    Active --> Client
    Client --> Hooks --> Policy
    Policy --> SQL
    Policy --> Gremlin
    Hooks --> SQL
    SQL --> Obs
    Gremlin --> Obs
```

---

## 13. 关键文件索引

| 用途 | 路径 |
|------|------|
| Schema / BaseSchema | `entpy/schema/base.py`, `field.py`, `edge.py` |
| IR 编译 | `entpy/ir/loader.py`, `graph.py`, `descriptor.py` |
| 注册表 | `entpy/runtime/registry.py` |
| CRUD | `entpy/runtime/builders.py`, `builders_async.py` |
| 谓词 → SQL/Gremlin | `entpy/runtime/predicate.py` |
| Spec 构建 | `entpy/runtime/spec_helpers.py` |
| SQL 执行 | `entpy/dialect/sqlalchemy/sqlgraph.py` |
| Gremlin 执行 | `entpy/dialect/gremlin/graph_ops.py` |
| DDL / 表结构 | `entpy/dialect/sqlalchemy/metadata.py` |
| 遍历 | `entpy/runtime/traverse.py` |
| Hook | `entpy/runtime/hook.py` |
| Interceptor | `entpy/runtime/interceptor.py` |
| Observer 集成 | `entpy/observer/hooks.py`, `discovery.py`, `integration.py` |
| Policy | `entpy/privacy/policy.py` |
| 收集 hooks/policies | `entpy/ir/policies.py` |
| Active | `entpy/active/bind.py`, `schema.py`, `queryset.py`, `entity.py` |
| 检索 | `entpy/search/builder.py`, `registry.py` |
| Client 入口 | `entpy/runtime/client.py` |

---

## 14. 简要结论

1. **架构**：声明式 Schema → IR Graph → Registry → Builder → Dialect；Active 层是 Client 的语法糖。
2. **谓词**：`F(User).age.gt(18)` **会下推**为 SQLAlchemy `WHERE` 或 Gremlin `has()`，由驱动生成最终 SQL/遍历，**不是**手写 SQL 字符串。
3. **函数不自动转 SQL**：只有 `Predicate` / EntQL 定义的过滤会编译；Policy、Observer、RRF 等均在 Python 运行时解释。
4. **写路径**：Hook（含 Observer 前置）→ Policy → Spec → DB → Observer 后置（`on_save` / `on_delete`）。
5. **读路径**：Policy → Interceptor → Predicate 下推 → DB → `Entity` 封装。
