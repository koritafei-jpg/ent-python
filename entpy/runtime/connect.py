"""数据库连接钩子：DSN、配置、环境变量、已有 Client、自定义扩展。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from entpy.schema.base import Schema

# 用户注册的全局钩子（优先于内置钩子）
_HOOKS: list[Any] = []


@dataclass
class ConnectRequest:
    """连接解析请求；各钩子按 ``match`` 决定是否处理。"""

    schemas: list[type[Schema]]
    async_: bool = False
    dsn: str | None = None
    storage: str = "sql"
    config: dict[str, Any] | None = None
    config_path: str | None = None
    env_prefix: str = "ENTPY_"
    client: Any | None = None
    owns_connection: bool = True
    observer_packages: list[str] | None = None
    runtime_hooks: list[Any] | None = None
    ctx: dict[str, Any] | None = None
    engine_kw: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


@runtime_checkable
class ConnectionHook(Protocol):
    """连接钩子：``match`` 选中后由 ``open`` 返回 ``Client`` / ``AsyncClient``。"""

    def match(self, request: ConnectRequest) -> bool: ...

    def open(self, request: ConnectRequest) -> Any: ...


def register_connection_hook(
    hook: ConnectionHook,
    *,
    prepend: bool = False,
) -> None:
    """注册全局连接钩子；``prepend=True`` 时优先于内置钩子。"""
    if prepend:
        _HOOKS.insert(0, hook)
    else:
        _HOOKS.append(hook)


def clear_connection_hooks() -> None:
    """清空已注册钩子（主要用于测试）。"""
    _HOOKS.clear()


def load_config(path: str | Path) -> dict[str, Any]:
    """从 JSON 文件加载连接配置（键：``dsn``、``storage``、``async``、``engine_kw``、``ctx``）。"""
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"config file must be a JSON object, got {type(data).__name__}")
    return data


def config_from_env(prefix: str = "ENTPY_") -> dict[str, Any]:
    """从环境变量读取连接配置（``{prefix}DSN``、``{prefix}STORAGE`` 等）。"""
    out: dict[str, Any] = {}
    dsn = os.environ.get(f"{prefix}DSN")
    if dsn:
        out["dsn"] = dsn
    storage = os.environ.get(f"{prefix}STORAGE")
    if storage:
        out["storage"] = storage
    if os.environ.get(f"{prefix}ASYNC", "").lower() in ("1", "true", "yes"):
        out["async"] = True
    return out


def _validate_client_kind(client: Any, *, async_: bool) -> None:
    from entpy.runtime.async_client import AsyncClient
    from entpy.runtime.client import Client

    if async_:
        if not isinstance(client, AsyncClient):
            raise TypeError(
                f"async_bind requires AsyncClient, got {type(client).__name__}"
            )
    elif isinstance(client, AsyncClient):
        raise TypeError("bind requires sync Client, got AsyncClient")
    elif not isinstance(client, Client):
        raise TypeError(f"expected Client, got {type(client).__name__}")


def _build_sync_client(request: ConnectRequest) -> Any:
    from entpy.runtime.client import Client

    if request.dsn is None:
        raise ValueError("sync connection requires dsn")
    return Client.open(
        request.dsn,
        schemas=request.schemas,
        storage=request.storage,
        observer_packages=request.observer_packages,
        ctx=request.ctx,
        **request.engine_kw,
    )


def _build_async_client(request: ConnectRequest) -> Any:
    from entpy.runtime.async_client import AsyncClient

    if request.dsn is None:
        raise ValueError("async connection requires dsn")
    return AsyncClient.open(
        request.dsn,
        schemas=request.schemas,
        storage=request.storage,
        observer_packages=request.observer_packages,
        ctx=request.ctx,
        **request.engine_kw,
    )


def _open_from_dsn(request: ConnectRequest) -> Any:
    if request.async_:
        return _build_async_client(request)
    return _build_sync_client(request)


class ExistingClientHook:
    """使用调用方已构造的 Client（连接池 / 应用级单例）。"""

    def match(self, request: ConnectRequest) -> bool:
        return request.client is not None

    def open(self, request: ConnectRequest) -> Any:
        client = request.client
        _validate_client_kind(client, async_=request.async_)
        return client


class ConfigConnectionHook:
    """从 ``config`` 字典或 ``config_path`` JSON 文件解析 DSN 后建连。"""

    def match(self, request: ConnectRequest) -> bool:
        return (
            request.client is None
            and (request.config is not None or request.config_path is not None)
        )

    def open(self, request: ConnectRequest) -> Any:
        cfg = dict(request.config or {})
        if request.config_path:
            cfg = {**load_config(request.config_path), **cfg}
        dsn = cfg.get("dsn")
        if not dsn:
            raise ValueError("config must include 'dsn'")
        nested = ConnectRequest(
            schemas=request.schemas,
            async_=request.async_,
            dsn=dsn,
            storage=str(cfg.get("storage", request.storage)),
            observer_packages=request.observer_packages,
            runtime_hooks=request.runtime_hooks,
            ctx=cfg.get("ctx", request.ctx),
            engine_kw={**request.engine_kw, **(cfg.get("engine_kw") or {})},
            owns_connection=request.owns_connection,
            source="config",
        )
        return _open_from_dsn(nested)


class EnvConnectionHook:
    """从环境变量 ``ENTPY_DSN`` / ``ENTPY_STORAGE`` 等读取（``source='env'`` 或仅有 env 无 dsn）。"""

    def match(self, request: ConnectRequest) -> bool:
        if request.client is not None:
            return False
        if request.source == "env":
            return True
        if request.dsn is not None or request.config or request.config_path:
            return False
        return bool(config_from_env(request.env_prefix).get("dsn"))

    def open(self, request: ConnectRequest) -> Any:
        cfg = config_from_env(request.env_prefix)
        dsn = cfg.get("dsn")
        if not dsn:
            raise RuntimeError(
                f"environment variable {request.env_prefix}DSN is not set"
            )
        nested = ConnectRequest(
            schemas=request.schemas,
            async_=request.async_,
            dsn=dsn,
            storage=str(cfg.get("storage", request.storage)),
            observer_packages=request.observer_packages,
            runtime_hooks=request.runtime_hooks,
            ctx=request.ctx,
            engine_kw=dict(request.engine_kw),
            owns_connection=request.owns_connection,
            source="env",
        )
        return _open_from_dsn(nested)


class DsnConnectionHook:
    """默认：直接使用 ``ConnectRequest.dsn``。"""

    def match(self, request: ConnectRequest) -> bool:
        return request.client is None and request.dsn is not None

    def open(self, request: ConnectRequest) -> Any:
        return _open_from_dsn(request)


def _default_hooks() -> list[ConnectionHook]:
    return [
        ExistingClientHook(),
        ConfigConnectionHook(),
        EnvConnectionHook(),
        DsnConnectionHook(),
    ]


def resolve_connection(
    request: ConnectRequest,
    *,
    extra_hooks: list[ConnectionHook] | None = None,
    apply_runtime_hooks: bool = True,
) -> Any:
    """按钩子链解析并返回 Client / AsyncClient。"""
    chain = list(_HOOKS) + _default_hooks()
    if extra_hooks:
        chain = list(extra_hooks) + chain
    for hook in chain:
        if hook.match(request):
            client = hook.open(request)
            if apply_runtime_hooks and request.runtime_hooks:
                client._hooks = list(request.runtime_hooks) + list(client._hooks)
            return client
    raise RuntimeError(
        "no connection hook matched: provide dsn=, config=, client=, "
        "source='env', or register_connection_hook(...)"
    )


def callable_connection_hook(
    match_fn: Callable[[ConnectRequest], bool],
    open_fn: Callable[[ConnectRequest], Any],
) -> ConnectionHook:
    """将 ``match`` / ``open`` 函数包装为 ``ConnectionHook``。"""

    class _Hook:
        def match(self, request: ConnectRequest) -> bool:
            return match_fn(request)

        def open(self, request: ConnectRequest) -> Any:
            return open_fn(request)

    return _Hook()
