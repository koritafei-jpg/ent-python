"""创建/更新时自动写入向量字段（对接外部 Embedding API）。"""

from __future__ import annotations

from typing import Any, Literal

from entpy.runtime.hook import AsyncHook, Hook
from entpy.runtime.mutation import Mutation, Op
from entpy.schema.base import SearchMixin
from entpy.search.embed_provider import EmbedAdapter, as_embed_provider

AsyncMode = Literal["auto", "sync", "async"]


def _collect_embed_text(mutation: Mutation, cfg: Any) -> str | None:
    parts: list[str] = []
    for name in cfg.text_fields:
        if name not in mutation.fields:
            continue
        val = mutation.fields.get(name)
        if val is not None and str(val).strip():
            parts.append(str(val))
    if not parts:
        return None
    return " ".join(parts)


def _text_fields_touched(mutation: Mutation, cfg: Any) -> bool:
    return any(name in mutation.fields for name in cfg.text_fields)


def _should_embed(mutation: Mutation) -> Any | None:
    schema = mutation.schema
    if not issubclass(schema, SearchMixin):
        return None
    cfg = schema.search_config()
    if cfg is None or not cfg.vector_field:
        return None
    if mutation.op not in (Op.CREATE, Op.UPDATE_ONE):
        return None
    return cfg


def _apply_embedding(
    mutation: Mutation, cfg: Any, adapter: EmbedAdapter, *, text: str
) -> None:
    vec = adapter.embed_sync([text])[0]
    mutation.fields[cfg.vector_field] = vec


async def _apply_embedding_async(
    mutation: Mutation, cfg: Any, adapter: EmbedAdapter, *, text: str
) -> None:
    vec = (await adapter.embed([text]))[0]
    mutation.fields[cfg.vector_field] = vec


def _zero_vector(mutation: Mutation, cfg: Any) -> list[float]:
    dim = 8
    for f in mutation.schema.fields():
        desc = getattr(f, "_d", f)
        if getattr(desc, "name", None) == cfg.vector_field:
            dim = getattr(desc, "vector_dimensions", None) or 8
            break
    return [0.0] * dim


def _clear_stale_vector(mutation: Mutation, cfg: Any) -> None:
    """文本字段被清空时写入零向量，避免保留陈旧 embedding（列多为 NOT NULL）。"""
    mutation.fields[cfg.vector_field] = _zero_vector(mutation, cfg)


def _process_embed_fields(
    mutation: Mutation, cfg: Any, adapter: EmbedAdapter
) -> None:
    if cfg.vector_field in mutation.fields and mutation.fields[cfg.vector_field] is not None:
        if not _text_fields_touched(mutation, cfg):
            return
    text = _collect_embed_text(mutation, cfg)
    if text:
        _apply_embedding(mutation, cfg, adapter, text=text)
    elif mutation.op is Op.UPDATE_ONE and _text_fields_touched(mutation, cfg):
        _clear_stale_vector(mutation, cfg)


async def _process_embed_fields_async(
    mutation: Mutation, cfg: Any, adapter: EmbedAdapter
) -> None:
    if cfg.vector_field in mutation.fields and mutation.fields[cfg.vector_field] is not None:
        if not _text_fields_touched(mutation, cfg):
            return
    text = _collect_embed_text(mutation, cfg)
    if text:
        await _apply_embedding_async(mutation, cfg, adapter, text=text)
    elif mutation.op is Op.UPDATE_ONE and _text_fields_touched(mutation, cfg):
        _clear_stale_vector(mutation, cfg)


def embed_on_save_hook(
    embedder: Any,
    *,
    async_mode: AsyncMode = "auto",
) -> Hook | AsyncHook:
    """持久化前根据可检索文本调用外部 Embedding 并写入向量字段。"""
    adapter = as_embed_provider(embedder)
    use_async = async_mode == "async" or (
        async_mode == "auto"
        and adapter.supports_async()
        and not adapter.supports_sync()
    )
    if use_async:
        return _build_async_hook(adapter)
    if not adapter.supports_sync():
        raise TypeError(
            f"{type(embedder).__name__!r} has no sync embed; use async_mode='async'"
        )
    return _build_sync_hook(adapter)


def embed_on_save_async_hook(embedder: Any) -> AsyncHook:
    """等价于 ``embed_on_save_hook(embedder, async_mode='async')``。"""
    hook = embed_on_save_hook(embedder, async_mode="async")
    if not isinstance(hook, AsyncHook):
        raise TypeError("embedder must support async embed")
    return hook


def _build_sync_hook(adapter: EmbedAdapter) -> Hook:
    @Hook
    def _hook(next_mutator, mutation: Mutation):
        cfg = _should_embed(mutation)
        if cfg is not None:
            _process_embed_fields(mutation, cfg, adapter)
        return next_mutator.mutate(mutation)

    return _hook


def _build_async_hook(adapter: EmbedAdapter) -> AsyncHook:
    @AsyncHook
    async def _hook(next_mutator, mutation: Mutation):
        cfg = _should_embed(mutation)
        if cfg is not None:
            await _process_embed_fields_async(mutation, cfg, adapter)
        return await next_mutator.mutate(mutation)

    return _hook
