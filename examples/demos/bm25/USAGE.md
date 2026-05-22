# Demo 2：BM25 全文检索

## 概述

演示 `search(Document).bm25_sync()`（在 `with bind(...):` 内）：

- 基础关键词检索（开发环境用 `postgres_ts`：SQLite 下降级为 `LIKE`）
- **BM25 + SQL 条件**（category / lang）
- 复杂管道（检索 → 过滤 → 分数阈值）
- **子表** `Section`（`document_id` FK）

> 生产环境可切换 `opensearch` / `pg_bm25` 后端；见 `SearchConfig.bm25_backend`。

## 数据模型

见 `examples/demos/search_schemas.py`：

- `documents`：title, category, lang, **content**（可检索）, **embedding**
- `sections`：document_id, heading, content（子表）

## 运行

```bash
cd python
python -m examples.demos.bm25.demo
```

## 初始化

```python
from entpy.active import bind, migrate, search
from examples.demos.search_schemas import Document, SEARCH_SCHEMAS
from examples.demos.search_seed import seed

with bind("sqlite:///:memory:", schemas=SEARCH_SCHEMAS):
    migrate()
    seed()
    sb = search(Document)
    hits = sb.bm25_sync("entpy runtime", top_k=5)
```

## 1. 基础 BM25 查询

```python
hits = sb.bm25_sync("entpy runtime", top_k=5)
for h in hits:
    print(h.id, h.score, h.text)
```

返回 `ScoredHit(id, score, source="bm25", text=...)`。

## 2. BM25 + 条件

检索与结构化条件**分两步**（推荐模式）：

```python
from examples.demos.common.search_helpers import filter_hits

raw = sb.bm25_sync("entpy runtime graph", top_k=10)
filtered = filter_hits(Document, raw, category="tech", lang="en")
```

`filter_hits` 用 `F(Document).id.in_(...)` + 字段等值在 SQL 层过滤。

## 3. 复杂查询

```python
raw = sb.bm25_sync("search", top_k=10)
filtered = filter_hits(Document, raw, category="tech")
filtered = [h for h in filtered if h.score >= 0.5]
```

可叠加业务排序、分页等。

## 4. 子表查询

```python
h = sb.bm25_sync("pgvector", top_k=1)[0]
doc = Document.get(id=h.id)
sections = Section.query(document_id=doc.id).all()
```

## 5. 切换 BM25 后端（生产）

```python
from entpy.search.backends.registry import get_bm25_backend

search(Chunk, bm25_backend=get_bm25_backend("opensearch"))
```

## 注意事项

| 环境 | 行为 |
|------|------|
| SQLite | `LIKE %query%`，非真 BM25 |
| PostgreSQL | `ts_rank` + `tsvector`，仍非真 BM25 |
| OpenSearch | 真 BM25（需安装 `opensearch-py`） |

## 相关测试

- `tests/search/test_bm25.py`
- `tests/search/test_hybrid.py`
