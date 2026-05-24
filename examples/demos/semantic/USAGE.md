# Demo 3：语义检索（向量）

## 概述

演示 `search(Document).semantic_sync()`（在 `with demo_bind(...):` 内）：

- 文本 → `Embedder` → 向量相似度
- **语义 + SQL 条件**
- 复杂 top-k + 过滤管道
- 子表 `Section`

PostgreSQL + pgvector 时走索引；SQLite 使用内存 brute-force 余弦相似度。

实体继承 `BaseSchema`：`id`（UUID）、`create_time`、`delete_time`；子表 `Section.document_id` 为 UUID 外键。

## 运行

```bash
cd python
python -m examples.demos.semantic.demo
```

## 依赖

```bash
pip install -e ".[search]"
# PostgreSQL 集成测试（可选）:
# docker compose -f docker-compose.pgvector.yml up -d
```

## 初始化

```python
from entpy.active import migrate, search
from examples.demos.common.connect import demo_bind
from examples.demos.semantic.models import Document, SEARCH_SCHEMAS
from examples.demos.semantic.seed import seed

with demo_bind(SEARCH_SCHEMAS):
    migrate()
    emb = seed()
    sb = search(Document)
```

## 1. 基础语义查询

```python
hits = sb.semantic_sync(
    "vector database embedding",
    embedder=emb,
    top_k=5,
)
```

也可直接传入向量：

```python
vec = emb.embed_sync(["my query"])[0]
hits = sb.semantic_sync(vec, top_k=5)
```

## 2. 语义 + 条件

```python
from examples.demos.common.search_helpers import filter_hits

raw = sb.semantic_sync("graph traversal", embedder=emb, top_k=10)
filtered = filter_hits(Document, raw, lang="en", category="tech")
```

## 3. 复杂查询

```python
raw = sb.semantic_sync("runtime ORM framework", embedder=emb, top_k=10)
filtered = filter_hits(Document, raw, category="tech", lang="en")
top3 = sorted(filtered, key=lambda h: h.score, reverse=True)[:3]
```

## 4. 子表

```python
for h in sb.semantic_sync("pgvector", embedder=emb, top_k=2):
    doc = Document.get(id=h.id)
    sections = Section.query(document_id=doc.id).all()
```

## Embedder 协议

实现 `embed_sync` / `embed` 即可接入 OpenAI、本地模型等：

```python
class MyEmbedder:
    def embed_sync(self, texts: list[str]) -> list[list[float]]: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

## 写入时自动 Embedding（可选）

在 `demo_bind` / `bind` / `async_bind` 的 `hooks=` 中注册 `embed_on_save_hook`，可对接任意外部 Embedding 服务：

```python
from entpy.active import migrate
from entpy.runtime.hooks import embed_on_save_hook
from entpy.search import callable_embedder
from examples.demos.common.connect import demo_bind

# 方式 1：直接传同步函数（HTTP 客户端封装）
def my_embed_api(texts: list[str]) -> list[list[float]]:
    # 调用 OpenAI / 本地模型 / 自建服务
    ...

with demo_bind(SCHEMAS, hooks=[embed_on_save_hook(my_embed_api)]):
    migrate()
    Chunk.create(path="/a", nchunk=0, data="...")  # 保存前自动写向量字段

# 方式 2：类实现 embed_sync / async embed
class MyEmbedder:
    def embed_sync(self, texts): ...
    async def embed(self, texts): ...

# 方式 3：callable_embedder 显式分离 sync/async
emb = callable_embedder(embed_sync=..., embed=...)
with demo_bind(SCHEMAS, hooks=[embed_on_save_hook(emb)]):
    ...
```

纯异步客户端用 `embed_on_save_hook(client, async_mode="async")` 或 `embed_on_save_async_hook(client)`。

## 相关测试

- `tests/search/test_semantic.py`
- `tests/search/test_embed_hook.py`
