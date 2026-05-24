# Demo 3：语义检索（向量）

## 概述

演示 `search(Document).semantic_sync()`（在 `with bind(...):` 内）：

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
from entpy.active import bind, migrate, search
from examples.demos.search_schemas import Document, SEARCH_SCHEMAS
from examples.demos.search_seed import seed

with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
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

需在打开连接时注册 hook；当前 `bind()` 尚未暴露 `hooks` 参数，可参考 `tests/search/test_embed_hook.py`，或扩展 `bind(..., hooks=[...])`。

## 相关测试

- `tests/search/test_semantic.py`
- `tests/search/test_embed_hook.py`
