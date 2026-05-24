"""Demo Observer 事件记录（供演示输出，无业务依赖）。"""

from __future__ import annotations

from typing import Any

_events: list[str] = []


def record(schema: str, hook: str, mutation: Any) -> None:
    _events.append(f"{schema}.{hook} id={mutation.id}")


def drain() -> list[str]:
    out = list(_events)
    _events.clear()
    return out
