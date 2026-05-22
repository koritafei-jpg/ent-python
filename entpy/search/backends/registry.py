"""可插拔 BM25 后端注册表。"""

from __future__ import annotations

from entpy.search.backends.base import BM25Backend
from entpy.search.backends.postgres_ts import PostgresTSBackend


_BACKENDS: dict[str, type] = {
    "postgres_ts": PostgresTSBackend,
}


def register_bm25_backend(name: str, cls: type) -> None:
    _BACKENDS[name] = cls


def get_bm25_backend(name: str) -> BM25Backend:
    if name == "opensearch":
        from entpy.search.backends.opensearch import OpenSearchBackend

        return OpenSearchBackend()
    cls = _BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"unknown bm25 backend {name!r}; registered: {list(_BACKENDS)}")
    return cls()
