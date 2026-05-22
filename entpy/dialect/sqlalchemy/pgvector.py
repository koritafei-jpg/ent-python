"""pgvector SQLAlchemy 类型（可选依赖）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.types import TypeDecorator, String, UserDefinedType


class VectorType(TypeDecorator):
    """有 pgvector 时用向量类型；SQLite 回退 JSON 文本。"""

    impl = String
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        super().__init__()
        self.dimensions = dimensions
        self._pgvector = None
        try:
            from pgvector.sqlalchemy import Vector  # type: ignore

            self._pgvector = Vector(dimensions)
        except ImportError:
            pass

    def load_dialect_impl(self, dialect):
        if self._pgvector is not None and dialect.name == "postgresql":
            return dialect.type_descriptor(self._pgvector)
        return dialect.type_descriptor(String())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if self._pgvector is not None and dialect.name == "postgresql":
            return value
        if isinstance(value, list):
            return json.dumps(value)
        return value

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
