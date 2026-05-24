"""外部 Embedding 服务统一接入（OpenAI、本地模型、HTTP 客户端等）。"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

SyncEmbedFunc = Callable[[list[str]], list[list[float]]]
AsyncEmbedFunc = Callable[[list[str]], Awaitable[list[list[float]]]]


@runtime_checkable
class EmbedProvider(Protocol):
    """框架识别的 Embedding 提供方（同步 + 可选异步）。"""

    def embed_sync(self, texts: list[str]) -> list[list[float]]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize_vectors(result: Any, n: int) -> list[list[float]]:
    if not isinstance(result, list) or len(result) != n:
        raise ValueError(
            f"embed must return list[list[float]] of length {n}, got {type(result).__name__}"
        )
    return result


class EmbedAdapter:
    """将多种外部 embed 实现适配为 ``embed_sync`` / ``embed``。"""

    def __init__(self, source: Any) -> None:
        if source is None:
            raise TypeError("embedder cannot be None")
        self._source = source
        self._sync_fn = self._resolve_sync()
        self._async_fn = self._resolve_async()

    def _resolve_sync(self) -> SyncEmbedFunc | None:
        if isinstance(self._source, EmbedAdapter):
            return self._source._sync_fn
        if callable(self._source) and not inspect.isclass(self._source):
            if inspect.iscoroutinefunction(self._source):
                return None
            return self._source
        embed_sync = getattr(self._source, "embed_sync", None)
        if callable(embed_sync) and not inspect.iscoroutinefunction(embed_sync):
            return embed_sync
        embed = getattr(self._source, "embed", None)
        if callable(embed) and not inspect.iscoroutinefunction(embed):
            return embed
        return None

    def _resolve_async(self) -> AsyncEmbedFunc | None:
        if isinstance(self._source, EmbedAdapter):
            return self._source._async_fn
        if callable(self._source) and not inspect.isclass(self._source):
            if inspect.iscoroutinefunction(self._source):
                return self._source
        embed = getattr(self._source, "embed", None)
        if callable(embed) and inspect.iscoroutinefunction(embed):
            return embed
        return None

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if self._sync_fn is None:
            raise TypeError(
                f"{type(self._source).__name__!r} has no sync embed; "
                "provide embed_sync, a sync embed(), or a sync callable"
            )
        return _normalize_vectors(self._sync_fn(texts), len(texts))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._async_fn is not None:
            return _normalize_vectors(await self._async_fn(texts), len(texts))
        return await asyncio.to_thread(self.embed_sync, texts)

    def supports_async(self) -> bool:
        return self._async_fn is not None

    def supports_sync(self) -> bool:
        return self._sync_fn is not None


def as_embed_provider(embedder: Any) -> EmbedAdapter:
    """将外部 embedder / 可调用对象包装为 ``EmbedAdapter``。"""
    if isinstance(embedder, EmbedAdapter):
        return embedder
    return EmbedAdapter(embedder)


def callable_embedder(
    *,
    embed_sync: SyncEmbedFunc | None = None,
    embed: AsyncEmbedFunc | None = None,
) -> EmbedAdapter:
    """用函数快速构造外部 Embedding 客户端（便于对接 HTTP API）。"""
    if embed_sync is None and embed is None:
        raise TypeError("provide embed_sync and/or embed")

    class _FnEmbedder:
        pass

    inst = _FnEmbedder()
    if embed_sync is not None:
        inst.embed_sync = embed_sync
    if embed is not None:
        inst.embed = embed
    return EmbedAdapter(inst)
