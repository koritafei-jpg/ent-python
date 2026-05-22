"""字段构建器。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from entpy.schema.search import FullText


class FieldType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    TIME = "time"
    JSON = "json"
    BYTES = "bytes"
    ENUM = "enum"
    UUID = "uuid"
    VECTOR = "vector"


@dataclass
class FieldDescriptor:
    name: str
    typ: FieldType
    optional: bool = False
    unique: bool = False
    immutable: bool = False
    nillable: bool = False
    default: Any = None
    default_func: Callable[[], Any] | None = None
    storage_key: str | None = None
    validators: list[Callable[[Any], None]] = dc_field(default_factory=list)
    searchable: FullText | None = None
    vector_dimensions: int | None = None
    enum_values: list[str] | None = None

    @property
    def column(self) -> str:
        return self.storage_key or self.name


class Field:
    """流式字段构建器。"""

    def __init__(self, descriptor: FieldDescriptor) -> None:
        self._d = descriptor

    def descriptor(self) -> FieldDescriptor:
        return self._d

    def optional(self) -> Field:
        self._d.optional = True
        return self

    def unique(self) -> Field:
        self._d.unique = True
        return self

    def immutable(self) -> Field:
        self._d.immutable = True
        return self

    def default(self, value: Any) -> Field:
        self._d.default = value
        return self

    def default_func(self, fn: Callable[[], Any]) -> Field:
        self._d.default_func = fn
        return self

    def storage_key(self, key: str) -> Field:
        self._d.storage_key = key
        return self

    def positive(self) -> Field:
        def _v(x: Any) -> None:
            if x is not None and int(x) <= 0:
                raise ValueError(f"{self._d.name}: must be positive")

        self._d.validators.append(_v)
        return self

    def match(self, pattern: re.Pattern[str]) -> Field:
        def _v(x: Any) -> None:
            if x is not None and not pattern.match(str(x)):
                raise ValueError(f"{self._d.name}: does not match pattern")

        self._d.validators.append(_v)
        return self

    def searchable(self, config: FullText | None = None) -> Field:
        self._d.searchable = config or FullText()
        return self


def _field(name: str, typ: FieldType, **kw: Any) -> Field:
    return Field(FieldDescriptor(name=name, typ=typ, **kw))


def bool_(name: str) -> Field:
    return _field(name, FieldType.BOOL)


def int_(name: str) -> Field:
    return _field(name, FieldType.INT)


def float_(name: str) -> Field:
    return _field(name, FieldType.FLOAT)


def string(name: str) -> Field:
    return _field(name, FieldType.STRING)


def text(name: str) -> Field:
    """长文本字段（存储与 string 相同）。"""
    return _field(name, FieldType.STRING)


def time(name: str) -> Field:
    return _field(name, FieldType.TIME)


def json_(name: str) -> Field:
    return _field(name, FieldType.JSON)


def vector(name: str, *, dimensions: int) -> Field:
    f = _field(name, FieldType.VECTOR)
    f._d.vector_dimensions = dimensions
    return f


def enum(name: str, values: list[str]) -> Field:
    f = _field(name, FieldType.ENUM)
    f._d.enum_values = values
    return f
