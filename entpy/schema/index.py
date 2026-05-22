"""索引构建器。"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass
class IndexDescriptor:
    fields: list[str] = dc_field(default_factory=list)
    unique: bool = False
    edges: list[str] = dc_field(default_factory=list)


class Index:
    def __init__(self, descriptor: IndexDescriptor) -> None:
        self._d = descriptor

    def descriptor(self) -> IndexDescriptor:
        return self._d

    def unique(self) -> Index:
        self._d.unique = True
        return self


def fields(*names: str) -> Index:
    return Index(IndexDescriptor(fields=list(names)))
