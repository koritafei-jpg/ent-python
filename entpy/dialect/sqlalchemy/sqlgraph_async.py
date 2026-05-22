"""sqlgraph 异步封装。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from entpy.dialect.sqlalchemy import sqlgraph
from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, QuerySpec, UpdateSpec


async def create_node(session: AsyncSession, tables: dict, spec: CreateSpec) -> Any:
    return await session.run_sync(lambda s: sqlgraph.create_node(s, tables, spec))


async def update_node(session: AsyncSession, tables: dict, spec: UpdateSpec) -> None:
    await session.run_sync(lambda s: sqlgraph.update_node(s, tables, spec))


async def delete_nodes(session: AsyncSession, tables: dict, spec: DeleteSpec) -> int:
    return await session.run_sync(lambda s: sqlgraph.delete_nodes(s, tables, spec))


async def query_nodes(session: AsyncSession, tables: dict, spec: QuerySpec) -> list[dict]:
    return await session.run_sync(lambda s: sqlgraph.query_nodes(s, tables, spec))
