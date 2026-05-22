"""为 Schema 谓词字段生成 .pyi 类型桩。"""

from __future__ import annotations

from pathlib import Path

from entpy.ir.graph import build_graph
from entpy.ir.loader import load_schemas
from entpy.schema.base import Schema


def generate_stubs(
    schemas: list[type[Schema]],
    target_dir: str | Path,
) -> list[Path]:
    """每个 Schema 输出一个带类型化 F() 字段的 .pyi。"""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    descriptors = load_schemas(schemas)
    for node in descriptors:
        lines = [
            '"""由 entpy.codegen.stubgen 自动生成，请勿编辑。"""',
            "from entpy.runtime.predicate import FieldRef, PredicateFactory",
            "",
            f"class {node.name}PredicateFactory(PredicateFactory):",
        ]
        lines.append("    id: FieldRef")
        for f in node.fields:
            lines.append(f"    {f.name}: FieldRef")
        lines.extend(["", ""])
        path = target / f"{node.name.lower()}_predicates.pyi"
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)

    init_lines = [
        '"""谓词类型桩包。"""',
        "from entpy.runtime.predicate import PredicateFactory",
        "",
    ]
    for node in descriptors:
        init_lines.append(
            f"from .{node.name.lower()}_predicates import {node.name}PredicateFactory as {node.name}F"
        )
    init_lines.append("")
    (target / "__init__.pyi").write_text("\n".join(init_lines), encoding="utf-8")
    written.append(target / "__init__.pyi")
    return written


def typed_predicate_factory(schema: type[Schema], registry) -> str:
    """返回供 mypy 使用的桩类名提示。"""
    return f"{schema.type_name()}PredicateFactory"
