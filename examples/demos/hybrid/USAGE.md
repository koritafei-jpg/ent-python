# Demo 4：BM25 + 语义混合检索（RRF）

## 概述

演示 `search(Document).hybrid_sync()`（在 `with bind(...):` 内）：

- 并行 BM25 + 语义两路召回
- **Reciprocal Rank Fusion (RRF)** 合并
- 混合 + SQL 条件
- 复杂业务管道
- 子表查询

## 运行

```bash
cd python
python -m examples.demos.hybrid.demo
```

## Schema 配置

`Document.search_config()` 中声明：

```python
SearchConfig(
    text_fields=["content"],
    vector_field="embedding",
    hybrid=Hybrid(bm25_backend="postgres_ts", rrf_k=60, top_k=10),
)
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

## 1. 基础混合查询

```python
hits = sb.hybrid_sync(
    "pgvector entpy runtime",
    embedder=emb,
    top_k=5,
)
```

`ScoredHit.source` 合并后为 `"hybrid"`，分数为 RRF 分数。

## 2. 混合 + 条件

```python
from examples.demos.common.search_helpers import filter_hits

raw = sb.hybrid_sync("graph database search", embedder=emb, top_k=10)
filtered = filter_hits(Document, raw, category="tech", lang="en")
```

## 3. 复杂查询

```python
raw = sb.hybrid_sync("vector ORM", embedder=emb, top_k=12, rrf_k=60)
filtered = filter_hits(Document, raw, category="tech")
filtered = sorted(filtered, key=lambda h: h.score, reverse=True)[:5]
# 再加载完整实体取 title 等
```

## 4. 子表

与 BM25 / 语义 demo 相同，按 `Section.document_id` 关联。

## 参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `top_k` | 10 | 最终返回条数 |
| `rrf_k` | 60 | RRF 常数 k，越大排名差异越平滑 |
| `embedder` | 必填 | 语义路需要 |

## 架构说明

- 混合逻辑在 `entpy.search.hybrid`，**不**进入 `sqlgraph` CRUD。
- CRUD 用 `Document.query()` / `Document.get()`；检索用 `search(Document)`。

## 相关测试

- `tests/search/test_hybrid.py`
- `tests/search/test_hybrid_rrf.py`
