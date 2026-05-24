"""ActiveEntity 绑定的 Update 构建器：save 时自动合并脏字段。"""

from __future__ import annotations

from typing import Any

from entpy.active.entity import ActiveEntity


def _edges_touched(builder: Any) -> set[str]:
    return set(getattr(builder, "_edges", {}).keys()) | set(
        getattr(builder, "_edge_replace", set())
    )


def _finish_bound_save(entity: ActiveEntity, builder: Any, row: Any) -> ActiveEntity:
    touched = _edges_touched(builder)
    if len(touched) == 1:
        entity._apply_persisted_row(row, edge=touched.pop())
    else:
        entity._apply_persisted_row(row)
    entity._dirty.clear()
    entity._refresh_json_snapshots()
    return entity


class BoundUpdateBuilder:
    """``entity.edit()`` 返回值：``save()`` 前写入未提交的脏字段。"""

    def __init__(self, entity: ActiveEntity, builder: Any) -> None:
        self._entity = entity
        self._builder = builder

    def set(self, name: str, value: Any) -> BoundUpdateBuilder:
        self._builder.set(name, value)
        return self

    def add(self, edge: str, *ids: Any) -> BoundUpdateBuilder:
        self._builder.add(edge, *ids)
        return self

    def set_edges(self, edge: str, *ids: Any) -> BoundUpdateBuilder:
        self._builder.set_edges(edge, *ids)
        return self

    def save(self) -> ActiveEntity:
        if self._entity._async:
            raise RuntimeError(
                "inside async_bind use: await entity.edit().add(...).save()"
            )
        self._entity._merge_dirty_into_builder(self._builder)
        row = self._builder.save()
        return _finish_bound_save(self._entity, self._builder, row)


class BoundAsyncUpdateBuilder(BoundUpdateBuilder):
    async def save(self) -> ActiveEntity:  # type: ignore[override]
        self._entity._merge_dirty_into_builder(self._builder)
        row = await self._builder.save()
        return _finish_bound_save(self._entity, self._builder, row)
