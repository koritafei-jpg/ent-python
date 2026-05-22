"""Gremlin 驱动（可选依赖 gremlinpython）。"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Iterator

from entpy.runtime.registry import Registry


class GremlinDriver:
    """gremlinpython DriverRemoteConnection 的薄封装。"""

    def __init__(self, url: str, registry: Registry) -> None:
        self._url = url
        self._registry = registry
        self._conn = None
        self._g = None

    @classmethod
    def from_url(cls, url: str, *, registry: Registry) -> GremlinDriver:
        return cls(url, registry)

    def _ensure(self) -> None:
        if self._g is not None:
            return
        try:
            from gremlinpython.driver.driver_remote_connection import DriverRemoteConnection
            from gremlinpython.process.anonymous_traversal import traversal
        except ImportError as e:
            raise ImportError("pip install entpy[gremlin]") from e
        self._conn = DriverRemoteConnection(self._url, "g")
        self._g = traversal().withRemote(self._conn)

    def dialect(self) -> str:
        return "gremlin"

    @property
    def g(self):
        self._ensure()
        return self._g

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    @contextmanager
    def session(self) -> Iterator[GremlinDriver]:
        self._ensure()
        yield self

    async def run(self, fn):
        return await asyncio.to_thread(fn)
