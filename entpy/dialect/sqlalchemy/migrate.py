"""Schema 迁移辅助。"""

from __future__ import annotations

from sqlalchemy import MetaData, text
from sqlalchemy.engine import Engine


def create_schema(engine: Engine, metadata: MetaData) -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    metadata.create_all(engine)
