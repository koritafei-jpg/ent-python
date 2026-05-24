"""使用 ContextVar 保存当前 bind 的 Client 与请求级 ctx。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_client_var: ContextVar[Any | None] = ContextVar("entpy_active_client", default=None)
_async_client_var: ContextVar[Any | None] = ContextVar("entpy_active_async_client", default=None)
_scope_ctx_var: ContextVar[dict[str, Any] | None] = ContextVar("entpy_scope_ctx", default=None)
_effective_ctx_sig: ContextVar[tuple[int, int, int] | None] = ContextVar(
    "entpy_effective_ctx_sig", default=None
)
_effective_ctx_merged: ContextVar[dict[str, Any] | None] = ContextVar(
    "entpy_effective_ctx_merged", default=None
)


def _invalidate_effective_ctx_cache() -> None:
    _effective_ctx_sig.set(None)
    _effective_ctx_merged.set(None)


def get_effective_ctx(client: Any) -> dict[str, Any]:
    """Client 基础 ctx 与 scope 叠加层合并（ContextVar 缓存，避免热路径重复拷贝）。"""
    overlay = _scope_ctx_var.get()
    base = client._ctx
    if not overlay:
        return base
    sig = (id(client), id(base), id(overlay))
    if _effective_ctx_sig.get() == sig:
        cached = _effective_ctx_merged.get()
        if cached is not None:
            return cached
    merged = {**base, **overlay}
    _effective_ctx_sig.set(sig)
    _effective_ctx_merged.set(merged)
    return merged


def push_scope_ctx(overlay: dict[str, Any]) -> Any:
    prev = _scope_ctx_var.get() or {}
    _invalidate_effective_ctx_cache()
    return _scope_ctx_var.set({**prev, **overlay})


def reset_scope_ctx(token: Any) -> None:
    _scope_ctx_var.reset(token)
    _invalidate_effective_ctx_cache()


def set_client(client: Any) -> Any:
    if _async_client_var.get() is not None:
        raise RuntimeError("cannot nest bind() inside async_bind()")
    return _client_var.set(client)


def reset_client(token: Any) -> None:
    _client_var.reset(token)


def get_client() -> Any:
    client = _client_var.get()
    if client is None:
        raise RuntimeError(
            "no active entpy bind — use 'with entpy.active.bind(...):' first"
        )
    return client


def set_async_client(client: Any) -> Any:
    if _client_var.get() is not None:
        raise RuntimeError("cannot nest async_bind() inside bind()")
    return _async_client_var.set(client)


def reset_async_client(token: Any) -> None:
    _async_client_var.reset(token)


def get_async_client() -> Any:
    client = _async_client_var.get()
    if client is None:
        raise RuntimeError(
            "no active entpy async bind — use 'async with entpy.active.async_bind(...):' first"
        )
    return client


def require_sync_client() -> Any:
    """ActiveSchema 同步 API 专用；``async_bind`` 下抛错。"""
    from entpy.runtime.client import Client

    client = get_bound_client()
    if not isinstance(client, Client):
        raise RuntimeError(
            "ActiveSchema 同步 API 需要 with bind(...)；"
            "async_bind 请使用 get_async_client() 或 await entity.persist()"
        )
    return client


def reject_async_module_api(api: str) -> None:
    """``traverse()`` / ``update()`` 等模块级同步辅助在 async_bind 下不可用。"""
    from entpy.runtime.async_client import AsyncClient

    client = get_bound_client()
    if isinstance(client, AsyncClient):
        raise RuntimeError(
            f"{api}() 为同步 API，async_bind 下请使用 get_async_client().{api.lstrip('_')}()"
        )


def get_bound_client() -> Any:
    """返回当前 bind 的同步或异步 Client（供 F() 等使用）。"""
    sync_client = _client_var.get()
    async_client = _async_client_var.get()
    if sync_client is not None and async_client is not None:
        raise RuntimeError("sync bind() and async_bind() are both active")
    if sync_client is not None:
        return sync_client
    if async_client is not None:
        return async_client
    raise RuntimeError(
        "no active entpy bind — use bind() or async_bind() first"
    )
