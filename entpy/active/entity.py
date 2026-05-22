"""Active 实体：save / persist / discard。"""

from __future__ import annotations

from typing import Any

from entpy.active.context import get_async_client, get_client
from entpy.runtime.entity import Entity
from entpy.schema.base import Schema


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
        super().__init__(schema, data, client)
        object.__setattr__(self, "_new", _new)
        object.__setattr__(self, "_async", _async)
        object.__setattr__(self, "_dirty", set())

    @classmethod
    def from_entity(cls, entity: Entity, *, _new: bool = False, _async: bool = False) -> ActiveEntity:
        inst = cls(entity._schema, entity._data, entity._client, _new=_new, _async=_async)
        object.__setattr__(inst, "_edges", dict(entity._edges))
        return inst

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        old = self._data.get(name)
        self._data[name] = value
        if old != value and not self._new:
            self._dirty.add(name)

    def save(self) -> ActiveEntity:
        if self._async:
            raise RuntimeError("use await entity.persist() inside async_bind")
        client = self._client or get_client()
        if self._new or self.id is None:
            saved = client.create(self._schema, **self._pending_fields()).save()
            object.__setattr__(self, "_new", False)
            self._data.update(saved._data)
            self._dirty.clear()
            object.__setattr__(self, "_client", client)
            return self
        if not self._dirty:
            return self
        builder = client.update(self._schema, self.id)
        for name in self._dirty:
            if name in self._data:
                builder.set(name, self._data[name])
        updated = builder.save()
        self._data.update(updated._data)
        self._dirty.clear()
        return self

    async def persist(self) -> ActiveEntity:
        client = self._client or get_async_client()
        if self._new or self.id is None:
            saved = await client.create(self._schema, **self._pending_fields()).save()
            object.__setattr__(self, "_new", False)
            self._data.update(saved._data)
            self._dirty.clear()
            object.__setattr__(self, "_client", client)
            object.__setattr__(self, "_async", True)
            return self
        if not self._dirty:
            return self
        builder = client.update(self._schema, self.id)
        for name in self._dirty:
            if name in self._data:
                builder.set(name, self._data[name])
        updated = await builder.save()
        self._data.update(updated._data)
        self._dirty.clear()
        return self

    def delete(self) -> None:
        if self._async:
            raise RuntimeError("use await entity.discard() inside async_bind")
        client = self._client or get_client()
        if self.id is None:
            raise ValueError("cannot delete unsaved entity")
        client.delete(self._schema).one(self.id).execute()

    async def discard(self) -> None:
        client = self._client or get_async_client()
        if self.id is None:
            raise ValueError("cannot delete unsaved entity")
        await client.delete(self._schema).one(self.id).execute()

    def _pending_fields(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if not k.startswith("_") and k != "id"}
