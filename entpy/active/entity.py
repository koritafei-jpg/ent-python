"""Active 实体：save / persist / discard。"""

from __future__ import annotations

import copy
import json
from typing import Any

from entpy.active.context import get_async_client, get_client
from entpy.runtime.entity import Entity
from entpy.runtime.validation import isolate_fields, json_field_names
from entpy.schema.base import Schema


def _json_field_names(schema: type[Schema]) -> frozenset[str]:
    return json_field_names(schema)


def _json_snapshot(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _copy_mutable(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return value


def _prepare_active_fields(schema: type[Schema], fields: dict[str, Any]) -> dict[str, Any]:
    return isolate_fields(schema, fields)


class ActiveEntity(Entity):
    """带脏字段跟踪的 save() 与删除辅助。"""

    def __init__(
        self,
        schema: type[Schema],
        data: dict[str, Any],
        client: Any = None,
        *,
        _new: bool = False,
        _async: bool = False,
    ) -> None:
        super().__init__(schema, isolate_fields(schema, data), client)
        object.__setattr__(self, "_new", _new)
        object.__setattr__(self, "_async", _async)
        object.__setattr__(self, "_dirty", set())
        object.__setattr__(self, "_json_snapshots", {})
        self._refresh_json_snapshots()

    @classmethod
    def from_entity(cls, entity: Entity, *, _new: bool = False, _async: bool = False) -> ActiveEntity:
        from entpy.runtime.async_client import AsyncClient

        if entity._client is not None and isinstance(entity._client, AsyncClient):
            _async = True
        data = dict(entity._data)
        for name in _json_field_names(entity._schema):
            if name in data:
                data[name] = copy.deepcopy(data[name])
        inst = cls(entity._schema, data, entity._client, _new=_new, _async=_async)
        object.__setattr__(
            inst, "_edges", {name: list(rows) for name, rows in entity._edges.items()}
        )
        return inst

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        old = self._data.get(name)
        value = _copy_mutable(value)
        if old != value and not self._new:
            client = self._client
            if client is None:
                try:
                    from entpy.active.context import get_bound_client

                    client = get_bound_client()
                except RuntimeError:
                    client = None
            if client is not None:
                from entpy.runtime.validation import is_immutable_noop

                if is_immutable_noop(
                    client._registry, self._schema, name, old, value
                ):
                    return
        self._data[name] = value
        if old != value and not self._new:
            self._dirty.add(name)
            if name in _json_field_names(self._schema):
                self._json_snapshots[name] = _json_snapshot(value)

    def _refresh_json_snapshots(self) -> None:
        snaps: dict[str, str] = {}
        for name in _json_field_names(self._schema):
            if name in self._data:
                snaps[name] = _json_snapshot(self._data[name])
        object.__setattr__(self, "_json_snapshots", snaps)

    def _mark_json_dirty_fields(self) -> None:
        if self._new:
            return
        for name in _json_field_names(self._schema):
            if name not in self._data:
                continue
            current = _json_snapshot(self._data[name])
            if self._json_snapshots.get(name) != current:
                self._dirty.add(name)

    def _apply_persisted_row(self, row: Entity, *, edge: str | None = None) -> None:
        """合并落库结果；失效 ``with_()`` 预加载的边缓存，避免 ``.groups`` 与库不一致。"""
        self._data.update(row._data)
        if edge is not None:
            self._edges.pop(edge, None)
        else:
            self._edges.clear()

    def _merge_dirty_into_builder(self, builder: Any) -> None:
        """将未 ``save()`` 的脏字段写入 UpdateBuilder（``edit`` / ``link`` 共用）。"""
        self._mark_json_dirty_fields()
        if not self._dirty:
            return
        client = self._client
        if client is None:
            client = get_async_client() if self._async else None
            if client is None:
                from entpy.active.context import require_sync_client

                client = require_sync_client()
        from entpy.runtime.validation import reject_immutable_updates

        pending = {name: self._data[name] for name in self._dirty if name in self._data}
        reject_immutable_updates(client._registry, self._schema, pending)
        for name, value in pending.items():
            builder.set(name, value)

    def save(self) -> ActiveEntity:
        if self._async:
            raise RuntimeError("use await entity.persist() inside async_bind")
        from entpy.active.context import require_sync_client

        client = self._client or require_sync_client()
        if self._new or self.id is None:
            saved = client.create(self._schema, **self._pending_fields()).save()
            object.__setattr__(self, "_new", False)
            self._apply_persisted_row(saved)
            self._dirty.clear()
            self._refresh_json_snapshots()
            object.__setattr__(self, "_client", client)
            return self
        self._mark_json_dirty_fields()
        if not self._dirty:
            return self
        from entpy.runtime.validation import reject_immutable_updates

        pending = {name: self._data[name] for name in self._dirty if name in self._data}
        reject_immutable_updates(client._registry, self._schema, pending)
        builder = client.update(self._schema, self.id)
        for name, value in pending.items():
            builder.set(name, value)
        updated = builder.save()
        self._apply_persisted_row(updated)
        self._dirty.clear()
        self._refresh_json_snapshots()
        return self

    async def persist(self) -> ActiveEntity:
        client = self._client or get_async_client()
        if self._new or self.id is None:
            saved = await client.create(self._schema, **self._pending_fields()).save()
            object.__setattr__(self, "_new", False)
            self._apply_persisted_row(saved)
            self._dirty.clear()
            self._refresh_json_snapshots()
            object.__setattr__(self, "_client", client)
            object.__setattr__(self, "_async", True)
            return self
        self._mark_json_dirty_fields()
        if not self._dirty:
            return self
        from entpy.runtime.validation import reject_immutable_updates

        pending = {name: self._data[name] for name in self._dirty if name in self._data}
        reject_immutable_updates(client._registry, self._schema, pending)
        builder = client.update(self._schema, self.id)
        for name, value in pending.items():
            builder.set(name, value)
        updated = await builder.save()
        self._apply_persisted_row(updated)
        self._dirty.clear()
        self._refresh_json_snapshots()
        return self

    def delete(self) -> None:
        if self._async:
            raise RuntimeError("use await entity.discard() inside async_bind")
        from entpy.active.context import require_sync_client

        client = self._client or require_sync_client()
        if self.id is None:
            raise ValueError("cannot delete unsaved entity")
        client.delete(self._schema).one(self.id).execute()

    async def discard(self) -> None:
        client = self._client or get_async_client()
        if self.id is None:
            raise ValueError("cannot delete unsaved entity")
        await client.delete(self._schema).one(self.id).execute()

    def edit(self) -> Any:
        """返回绑定的 Update 构建器；``save()`` 会一并提交脏字段。

        同步：``u.edit().set("age", 2).save()`` / ``u.edit().add("groups", g.id).save()``
        异步：``await u.edit().set_edges("groups", g.id).save()``
        """
        from entpy.active.bound_update import BoundAsyncUpdateBuilder, BoundUpdateBuilder

        if self._new or self.id is None:
            raise ValueError("cannot edit unsaved entity; use save() first")
        if self._async:
            client = self._client or get_async_client()
            inner = client.update(self._schema, self.id)
            return BoundAsyncUpdateBuilder(self, inner)
        from entpy.active.context import require_sync_client

        client = self._client or require_sync_client()
        return BoundUpdateBuilder(self, client.update(self._schema, self.id))

    def link(self, edge: str, *peer_ids: Any) -> ActiveEntity:
        """追加边关联（等价 ``edit().add(edge, *peer_ids).save()``，含脏字段）。"""
        if self._async:
            raise RuntimeError(
                "inside async_bind use: await entity.edit().add(edge, *ids).save()"
            )
        self.edit().add(edge, *peer_ids).save()
        return self

    def set_links(self, edge: str, *peer_ids: Any) -> ActiveEntity:
        """M2M 边全量替换（等价 ``edit().set_edges(...).save()``，含脏字段）。"""
        if self._async:
            raise RuntimeError(
                "inside async_bind use: await entity.edit().set_edges(edge, *ids).save()"
            )
        self.edit().set_edges(edge, *peer_ids).save()
        return self

    def _pending_fields(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if not k.startswith("_") and k != "id"}
