"""使用 ContextVar 保存当前 bind 的 Client。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_client_var: ContextVar[Any | None] = ContextVar("entpy_active_client", default=None)
_async_client_var: ContextVar[Any | None] = ContextVar("entpy_active_async_client", default=None)


def set_client(client: Any) -> Any:
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


def get_bound_client() -> Any:
    """返回当前 bind 的同步或异步 Client（供 F() 等使用）。"""
    async_client = _async_client_var.get()
    sync_client = _client_var.get()
    if sync_client is not None:
        return sync_client
    if async_client is not None:
        return async_client
    raise RuntimeError(
        "no active entpy bind — use bind() or async_bind() first"
    )
