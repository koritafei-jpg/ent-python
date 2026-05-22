"""薄封装代码生成，委托给 entpy.runtime。"""

from __future__ import annotations

from pathlib import Path

from entpy.ir.loader import load_schemas
from entpy.schema.base import Schema


def generate_thin_wrappers(
    schemas: list[type[Schema]],
    target_dir: str | Path,
    *,
    package: str = "ent_generated",
) -> list[Path]:
    """生成包装 Client 的薄 Python 模块，便于 IDE 使用。"""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    init = target / "__init__.py"
    init.write_text(
        f'"""由 entpy 生成 — 委托 entpy.runtime 的薄封装。"""\n'
        f"from {package}.client import Client\n",
        encoding="utf-8",
    )
    written.append(init)

    descriptors = load_schemas(schemas)
    imports = sorted({s.__module__ for s in schemas})
    import_lines = [f"import {m}" for m in imports]
    schema_refs = [f"{s.__module__}.{s.__name__}" for s in schemas]

    client_py = [
        '"""薄 Client — 内部调用 entpy.runtime.Client。"""',
        "from __future__ import annotations",
        "from entpy.runtime import Client as _RuntimeClient",
        "",
        *import_lines,
        "",
        f"SCHEMAS = [{', '.join(schema_refs)}]",
        "",
        "class Client(_RuntimeClient):",
        "    @classmethod",
        "    def open(cls, dsn: str, **kwargs):",
        '        kwargs.setdefault("schemas", SCHEMAS)',
        "        return super().open(dsn, **kwargs)",
        "",
    ]
    for d in descriptors:
        snake = _snake(d.name)
        ref = f"{d.schema_type.__module__}.{d.schema_type.__name__}"
        client_py.extend(
            [
                f"    def create_{snake}(self, **fields):",
                f"        return self.create({ref}, **fields)",
                f"    def query_{snake}(self):",
                f"        return self.query({ref})",
                "",
            ]
        )
    path = target / "client.py"
    path.write_text("\n".join(client_py), encoding="utf-8")
    written.append(path)
    return written


def _snake(name: str) -> str:
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
