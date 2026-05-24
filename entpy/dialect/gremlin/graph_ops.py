"""Gremlin 图存储 CRUD 操作。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from entpy.dialect.gremlin.labels import edge_label, vertex_label
from entpy.dialect.sqlalchemy.spec import CreateSpec, DeleteSpec, EdgeSpec, QuerySpec, UpdateSpec
from entpy.ir.graph import ResolvedEdge
from entpy.runtime.predicate import Predicate
from entpy.runtime.registry import Registry
from entpy.schema.edge import RelType


def create_node(g, registry: Registry, spec: CreateSpec) -> Any:
    vid = create_vertex(g, spec.table, spec.fields)
    for edge in spec.edges:
        _link_edge(g, registry, vid, edge)
    return vid


def create_vertex(g, label: str, properties: dict[str, Any]) -> Any:
    t = g.addV(label)
    for k, v in properties.items():
        if k == "id":
            continue
        t = t.property(k, _gremlin_value(v))
    result = t.next()
    return _vertex_id(result)


def update_node(g, registry: Registry, spec: UpdateSpec) -> dict[str, Any] | None:
    """更新顶点与边，返回最新属性（字段更新与 ``valueMap`` 同次遍历，避免额外 ``get_by_id``）。"""
    vid = spec.id
    label = spec.table
    if not g.V(vid).hasLabel(label).hasNext():
        return None
    row: dict[str, Any] | None = None
    if spec.fields:
        trav = g.V(vid).hasLabel(label)
        for k, v in spec.fields.items():
            trav = trav.property(k, _gremlin_value(v))
        row = _vm_to_dict(trav.valueMap(True).next())
    for edge in spec.edges:
        _link_edge(g, registry, vid, edge)
    if row is not None:
        return row
    rows = g.V(vid).hasLabel(label).valueMap(True).toList()
    if not rows:
        return None
    return _vm_to_dict(rows[0])


def delete_nodes(g, registry: Registry, spec: DeleteSpec) -> int:
    label = spec.table
    if spec.ids:
        count = 0
        for vid in spec.ids:
            t = g.V(vid).hasLabel(label)
            if t.hasNext():
                t.drop().iterate()
                count += 1
        return count
    t = g.V().hasLabel(label)
    for pred in spec.predicates:
        if isinstance(pred, Predicate):
            t = pred.apply_gremlin(t)
    count = t.count().next()
    t.drop().iterate()
    return int(count)


def query_nodes(
    g,
    registry: Registry,
    spec: QuerySpec,
    *,
    gremlin_preds: list[Predicate] | None = None,
) -> list[dict]:
    label = spec.table
    t = g.V().hasLabel(label)
    preds = gremlin_preds or []
    for pred in preds:
        t = pred.apply_gremlin(t)
    for pred in spec.predicates:
        if isinstance(pred, Predicate):
            t = pred.apply_gremlin(t)
    if spec.limit is not None:
        t = t.limit(spec.limit)
    rows = [_vm_to_dict(r) for r in t.valueMap(True).toList()]
    if spec.with_edges:
        for row in rows:
            row["_edges"] = {}
            for ename in spec.with_edges:
                re = registry.resolve_edge(_schema_for_label(registry, label), ename)
                if re is None:
                    continue
                peers = _load_edge_neighbors(g, registry, row["id"], re)
                row["_edges"][ename] = peers
    return rows


def traverse_neighbors(
    g, registry: Registry, *, owner_label: str, owner_id: Any, edge: ResolvedEdge
) -> list[dict]:
    return _load_edge_neighbors(g, registry, owner_id, edge)


def traverse_chain(
    g,
    registry: Registry,
    *,
    owner_id: Any,
    owner_label: str,
    edges: list[ResolvedEdge],
) -> list[dict]:
    """Gremlin 多跳 ``out`` 链，返回终点顶点属性。"""
    t = g.V(owner_id).hasLabel(owner_label)
    for edge in edges:
        t = _gremlin_out_step(t, edge)
    return [_vm_to_dict(r) for r in t.valueMap(True).toList()]


def traverse_chain_values(
    g,
    registry: Registry,
    *,
    owner_id: Any,
    owner_label: str,
    edges: list[ResolvedEdge],
    field: str,
) -> list[Any]:
    """Gremlin 多跳链后投影单字段。"""
    t = g.V(owner_id).hasLabel(owner_label)
    for edge in edges:
        t = _gremlin_out_step(t, edge)
    raw = t.values(field).toList()
    return [_flatten_value(v) for v in raw]


def clear_vertices(g, labels: list[str]) -> None:
    """按标签删除全部顶点。"""
    for label in labels:
        g.V().hasLabel(label).drop().iterate()


def get_by_id(g, label: str, vid: Any) -> dict | None:
    rows = g.V(vid).hasLabel(label).valueMap(True).toList()
    if not rows:
        return None
    return _vm_to_dict(rows[0])


def _link_edge(g, registry: Registry, from_id: Any, edge: EdgeSpec) -> None:
    re = _resolve_edge_spec(registry, edge)
    if re is None:
        return
    el = edge_label(re)
    for peer_id in edge.ids:
        if re.rel == RelType.M2M:
            from gremlinpython.process.graph_traversal import __

            exists = (
                g.V(from_id)
                .outE(el)
                .where(__.inV().hasId(peer_id))
                .hasNext()
            )
            if not exists:
                g.V(from_id).addE(el).to(g.V(peer_id)).iterate()
            continue
        elif re.fk_columns and re.rel in (RelType.O2M, RelType.M2O, RelType.O2O):
            fk = re.fk_columns[0]
            if re.rel == RelType.O2M and not re.inverse:
                g.V(peer_id).property(fk, from_id).iterate()
            elif re.rel == RelType.M2O and re.inverse:
                g.V(peer_id).property(fk, from_id).iterate()
            else:
                g.V(from_id).addE(el).to(g.V(peer_id)).iterate()
        elif re.rel in (RelType.O2M, RelType.O2O) and not re.inverse:
            g.V(from_id).addE(el).to(g.V(peer_id)).iterate()
        else:
            g.V(from_id).addE(el).to(g.V(peer_id)).iterate()


def _gremlin_out_step(t, edge: ResolvedEdge):
    """在 Gremlin 遍历上追加一跳（与 _load_edge_neighbors 语义一致）。"""
    el = edge_label(edge)
    if edge.rel == RelType.M2M:
        return t.out(el)
    if edge.fk_columns and edge.rel == RelType.O2M and not edge.inverse:
        fk = edge.fk_columns[0]
        peer_label = vertex_label(edge.peer)
        return (
            t.as_("src")
            .V()
            .hasLabel(peer_label)
            .has(fk, t.select("src").by("id"))
        )
    if edge.rel == RelType.O2M and not edge.inverse:
        return t.out(el)
    if edge.fk_columns:
        fk = edge.fk_columns[0]
        peer_label = vertex_label(edge.peer)
        return (
            t.as_("src")
            .V()
            .hasLabel(peer_label)
            .has(fk, t.select("src").by("id"))
        )
    return t.out(el)


def _load_edge_neighbors(
    g, registry: Registry, owner_id: Any, edge: ResolvedEdge
) -> list[dict]:
    t = g.V(owner_id)
    t = _gremlin_out_step(t, edge)
    return [_vm_to_dict(r) for r in t.valueMap(True).toList()]


def _flatten_value(v: Any) -> Any:
    if isinstance(v, list) and len(v) == 1:
        return v[0]
    return v


def _resolve_edge_spec(registry: Registry, edge: EdgeSpec) -> ResolvedEdge | None:
    for re in registry.graph.edges:
        if re.name == edge.name and re.peer.resolved_table() == edge.peer_table:
            return re
    return None


def _schema_for_label(registry: Registry, label: str):
    for st in registry.nodes:
        if registry.label_for(st) == label:
            return st
    raise ValueError(f"unknown label {label!r}")


def _vertex_id(result: Any) -> Any:
    if isinstance(result, dict):
        return result.get("id", result.get("T.id"))
    return getattr(result, "id", result)


def _gremlin_value(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _vm_to_dict(vm: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in vm.items():
        key = k if isinstance(k, str) else getattr(k, "name", str(k))
        if key in ("id", "T.id"):
            out["id"] = v[0] if isinstance(v, list) and len(v) == 1 else v
            continue
        if isinstance(v, list) and len(v) == 1:
            out[key] = v[0]
        else:
            out[key] = v
    if "id" not in out and "T.id" in vm:
        tid = vm["T.id"]
        out["id"] = tid[0] if isinstance(tid, list) else tid
    return out
