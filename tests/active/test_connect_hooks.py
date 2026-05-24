"""连接钩子：DSN / 配置 / 环境变量 / 已有 Client / 自定义。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from entpy.active import (
    bind,
    bind_client,
    clear_connection_hooks,
    config_from_env,
    load_config,
    register_connection_hook,
    resolve_connection,
)
from entpy.runtime.client import Client
from entpy.runtime.connect import ConnectRequest, callable_connection_hook
from examples.start.models import User, SCHEMAS


@pytest.fixture(autouse=True)
def _reset_hooks():
    clear_connection_hooks()
    yield
    clear_connection_hooks()


def test_bind_via_config_dict():
    with bind(config={"dsn": "sqlite:///:memory:"}, schemas=SCHEMAS):
        from entpy.active import migrate

        migrate()
        u = User.create(name="cfg", age=1)
        assert u.name == "cfg"


def test_bind_via_config_file(tmp_path: Path):
    path = tmp_path / "db.json"
    path.write_text(
        json.dumps({"dsn": "sqlite:///:memory:", "storage": "sql"}),
        encoding="utf-8",
    )
    with bind(config=str(path), schemas=SCHEMAS):
        from entpy.active import migrate

        migrate()
        assert User.query(name="missing").first() is None


def test_bind_via_env(monkeypatch):
    monkeypatch.setenv("ENTPY_DSN", "sqlite:///:memory:")
    with bind(schemas=SCHEMAS, source="env"):
        from entpy.active import migrate

        migrate()
        User.create(name="env", age=1)


def test_bind_client_does_not_close_app_client():
    app = Client.open("sqlite:///:memory:", schemas=SCHEMAS)
    app.migrate()
    with bind_client(app, lifecycle="app"):
        User.create(name="pooled", age=1)
    row = app.query(User).where(app.F(User).name.eq("pooled")).first()
    assert row is not None
    app.close()


def test_custom_connection_hook():
    seen: list[str] = []

    def match(req: ConnectRequest) -> bool:
        return req.source == "custom"

    def open_req(req: ConnectRequest) -> Client:
        seen.append("open")
        return Client.open("sqlite:///:memory:", schemas=req.schemas)

    register_connection_hook(
        callable_connection_hook(match, open_req),
        prepend=True,
    )
    with bind(schemas=SCHEMAS, source="custom"):
        from entpy.active import migrate

        migrate()
    assert seen == ["open"]


def test_resolve_connection_dsn():
    req = ConnectRequest(schemas=SCHEMAS, dsn="sqlite:///:memory:")
    client = resolve_connection(req)
    client.migrate()
    client.close()


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("ENTPY_DSN", "postgresql://localhost/db")
    monkeypatch.setenv("ENTPY_STORAGE", "sql")
    cfg = config_from_env()
    assert cfg["dsn"] == "postgresql://localhost/db"
    assert cfg["storage"] == "sql"


def test_load_config(tmp_path: Path):
    p = tmp_path / "c.json"
    p.write_text('{"dsn": "sqlite:///:memory:"}', encoding="utf-8")
    assert load_config(p)["dsn"] == "sqlite:///:memory:"
