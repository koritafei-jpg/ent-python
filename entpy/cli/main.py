"""entpy 命令行工具。"""

from __future__ import annotations

import typer

app = typer.Typer(help="entpy — runtime-first entity framework")


@app.command()
def version() -> None:
    from entpy import __version__

    typer.echo(f"entpy {__version__}")


@app.command()
def describe() -> None:
    typer.echo("entpy: define Schema classes and use Client.open(schemas=...)")


stubs_app = typer.Typer(help="Generate .pyi predicate stubs")
codegen_app = typer.Typer(help="Optional thin codegen")


@stubs_app.command("generate")
def stubs_generate(
    module: str = typer.Argument(..., help="Python module with SCHEMAS list or Schema classes"),
    target: str = typer.Option("entpy_stubs", "--target", "-t"),
) -> None:
    """生成 F(Schema) 字段访问器的 .pyi 类型桩。"""
    import importlib

    mod = importlib.import_module(module)
    schemas = getattr(mod, "SCHEMAS", None)
    if schemas is None:
        from entpy.schema.base import Schema
        import inspect

        schemas = [
            obj
            for _, obj in inspect.getmembers(mod, inspect.isclass)
            if issubclass(obj, Schema) and obj is not Schema
        ]
    from entpy.codegen.stubgen import generate_stubs

    paths = generate_stubs(schemas, target)
    typer.echo(f"Wrote {len(paths)} stub files to {target}")


@codegen_app.command("thin")
def codegen_thin(
    module: str = typer.Argument(...),
    target: str = typer.Option("ent_generated", "--target", "-t"),
) -> None:
    """生成 Client 薄封装模块。"""
    import importlib

    mod = importlib.import_module(module)
    schemas = getattr(mod, "SCHEMAS")
    from entpy.codegen.thin import generate_thin_wrappers

    paths = generate_thin_wrappers(schemas, target, package=target.replace("/", "."))
    typer.echo(f"Wrote {len(paths)} files to {target}")


search_app = typer.Typer(help="Search indexing utilities")


def _load_schemas(module: str) -> list:
    import importlib
    import inspect

    from entpy.schema.base import Schema

    mod = importlib.import_module(module)
    schemas = getattr(mod, "SCHEMAS", None)
    if schemas is None:
        schemas = [
            obj
            for _, obj in inspect.getmembers(mod, inspect.isclass)
            if issubclass(obj, Schema) and obj is not Schema
        ]
    return schemas


def _resolve_schema(schemas: list, name: str):
    for s in schemas:
        if s.type_name() == name or s.__name__ == name:
            return s
    raise typer.BadParameter(f"schema {name!r} not found in module")


def _embedder_from_name(name: str, dim: int):
    if name == "mock":
        from entpy.search import MockEmbedder

        return MockEmbedder(dim=dim)
    raise typer.BadParameter(f"unknown embedder {name!r}; use: mock")


@search_app.command("reindex")
def search_reindex(
    module: str = typer.Argument(..., help="Python module with SCHEMAS (e.g. examples.rag.models)"),
    schema: str = typer.Option(..., "--schema", "-s", help="Searchable schema class name"),
    dsn: str = typer.Option(..., "--dsn", help="SQL database URL"),
    embedder: str = typer.Option("mock", "--embedder", "-e", help="Embedder: mock"),
    dimensions: int = typer.Option(8, "--dim", help="Vector dimensions for mock embedder"),
    batch_size: int = typer.Option(32, "--batch-size", "-b"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Count rows without writing"),
) -> None:
    """对所有行按 text_fields 重新计算 vector_field（仅 SQL 存储）。"""
    schemas = _load_schemas(module)
    schema_cls = _resolve_schema(schemas, schema)
    emb = _embedder_from_name(embedder, dimensions)

    from entpy.runtime import Client
    from entpy.search.reindex import reindex_sync

    client = Client.open(dsn, schemas=schemas)
    client.migrate()
    n = reindex_sync(client, schema_cls, emb, batch_size=batch_size, dry_run=dry_run)
    typer.echo(f"reindexed {n} row(s) on {schema_cls.type_name()}" + (" (dry-run)" if dry_run else ""))


app.add_typer(stubs_app, name="stubs")
app.add_typer(codegen_app, name="generate")
app.add_typer(search_app, name="search")


if __name__ == "__main__":
    app()
