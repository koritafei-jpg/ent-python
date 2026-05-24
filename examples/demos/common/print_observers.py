"""打印 demo Observer 事件摘要。"""

from __future__ import annotations

from examples.demos.common.observer_log import drain


def print_observer_events(*, limit: int = 12) -> None:
    events = drain()
    if not events:
        return
    print("\n=== Observer (on_save / on_delete) ===")
    for line in events[:limit]:
        print(f"  {line}")
    if len(events) > limit:
        print(f"  ... +{len(events) - limit} more")
