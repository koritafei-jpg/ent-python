"""运行时 Hook 工厂（对外稳定接口）。"""

from entpy.runtime.hooks.embed_on_save import (
    embed_on_save_async_hook,
    embed_on_save_hook,
)

__all__ = [
    "embed_on_save_hook",
    "embed_on_save_async_hook",
]
