"""同步/异步 Client 共用的 Create/Update 规格构建。"""

from __future__ import annotations

from typing import Any

from entpy.dialect.sqlalchemy.spec import CreateSpec, EdgeSpec, UpdateSpec
from entpy.schema.base import Schema
from entpy.schema.edge import RelType
from entpy.runtime.registry import Registry


def _require_edge(registry: Registry, schema: type[Schema], ename: str) -> Any:
    re = registry.resolve_edge(schema, ename)
    if re is None:
        raise ValueError(
            f"unknown edge {ename!r} on {schema.type_name()}"
        )
    return re


def create_spec(registry: Registry, schema: type[Schema], fields: dict, edges: dict) -> CreateSpec:
    node = registry.node_for(schema)
    edge_specs = []
    for ename, ids in edges.items():
        re = _require_edge(registry, schema, ename)
        if re.rel == RelType.M2M:
            edge_specs.append(
                EdgeSpec(
                    rel=re.rel,
                    name=ename,
                    peer_table=re.peer.resolved_table(),
                    ids=ids,
                    join_table=re.join_table,
                    join_columns=re.join_columns,
                )
            )
        else:
            edge_specs.append(
                EdgeSpec(
                    rel=re.rel,
                    name=ename,
                    peer_table=re.peer.resolved_table(),
                    ids=ids,
                    fk_columns=re.fk_columns,
                )
            )
    return CreateSpec(table=node.resolved_table(), fields=fields, edges=edge_specs)


def update_spec(
    registry: Registry, schema: type[Schema], id: Any, fields: dict, edges: dict
) -> UpdateSpec:
    node = registry.node_for(schema)
    edge_specs = []
    for ename, ids in edges.items():
        if not ids:
            continue
        re = _require_edge(registry, schema, ename)
        edge_specs.append(
            EdgeSpec(
                rel=re.rel,
                name=ename,
                peer_table=re.peer.resolved_table(),
                ids=ids,
                fk_columns=re.fk_columns,
                join_table=re.join_table,
                join_columns=re.join_columns,
            )
        )
    return UpdateSpec(table=node.resolved_table(), id=id, fields=fields, edges=edge_specs)
