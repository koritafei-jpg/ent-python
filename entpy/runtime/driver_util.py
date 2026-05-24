"""驱动类型检测（避免 runtime 与 dialect 循环导入）。"""

from __future__ import annotations

from typing import Any


def is_async_sql_driver(client: Any) -> bool:
    from entpy.dialect.sqlalchemy.async_driver import AsyncSQLAlchemyDriver

    return isinstance(client._driver, AsyncSQLAlchemyDriver)
